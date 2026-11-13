"""H7 diagnostic: contextual soft edge cost with relation-guided domains."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Callable

from factkg_e1_pilot import api_key_for, call_model, digest, read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder, has_annotated_path, relation_text

from soft_isomorphism.matching import label_distance

NODE_WEIGHT = 0.3
EDGE_WEIGHT = 0.7
NULL_COST = 0.8
ROUNDS = 2
EXPANSION_PER_EDGE = 5
DOMAIN_LIMIT = 20
BEAM_WIDTH = 64
TOP_K = 50
ARMS = ("B1", "B4", "C7", "H7")
READER_ARMS = ("B4", "C7")


def directed_arcs(triples: list[dict]) -> list[dict]:
    arcs = []
    for triple in triples:
        arcs.append(
            {
                "source": triple["source"],
                "relation": triple["relation"],
                "target": triple["target"],
                "evidence": triple,
            }
        )
        arcs.append(
            {
                "source": triple["target"],
                "relation": "~" + triple["relation"],
                "target": triple["source"],
                "evidence": triple,
            }
        )
    return arcs


def edge_text(source: str, relation: str, target: str) -> str:
    readable = relation_text(relation)
    if relation.startswith("~"):
        readable = "inverse " + readable
    return (
        f"source: {source.replace('_', ' ')}; "
        f"relation: {readable}; target: {target.replace('_', ' ')}"
    )


def query_edge_text(edge: dict, labels: dict[str, str]) -> str:
    return edge_text(labels[edge["source"]], edge["relation"], labels[edge["target"]])


def indices(arcs: list[dict]) -> tuple[dict, dict, dict]:
    outgoing: dict[str, list[dict]] = defaultdict(list)
    incoming: dict[str, list[dict]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for arc in arcs:
        outgoing[arc["source"]].append(arc)
        incoming[arc["target"]].append(arc)
        by_pair[arc["source"], arc["target"]].append(arc)
    return outgoing, incoming, by_pair


def expand_domains(
    graph: dict,
    domains: dict[str, list[str]],
    arcs: list[dict],
    similarity: Callable[[str, str], float],
) -> dict[str, list[str]]:
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    outgoing, incoming, _ = indices(arcs)
    result = {node: list(dict.fromkeys(values)) for node, values in domains.items()}
    for _ in range(ROUNDS):
        proposals: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for edge in graph["edges"]:
            query_text = query_edge_text(edge, labels)
            forward = [
                (similarity(query_text, edge_text(a["source"], a["relation"], a["target"])), a)
                for source in result.get(edge["source"], [])
                for a in outgoing.get(source, [])
            ]
            backward = [
                (similarity(query_text, edge_text(a["source"], a["relation"], a["target"])), a)
                for target in result.get(edge["target"], [])
                for a in incoming.get(target, [])
            ]
            for score, arc in sorted(
                forward,
                key=lambda item: (-item[0], item[1]["relation"], item[1]["target"]),
            )[:EXPANSION_PER_EDGE]:
                proposals[edge["target"]].append((score, arc["target"]))
            for score, arc in sorted(
                backward,
                key=lambda item: (-item[0], item[1]["relation"], item[1]["source"]),
            )[:EXPANSION_PER_EDGE]:
                proposals[edge["source"]].append((score, arc["source"]))
        for node_id, values in proposals.items():
            ranked = [
                identifier for _, identifier in sorted(values, key=lambda item: (-item[0], item[1]))
            ]
            result[node_id] = list(dict.fromkeys([*result[node_id], *ranked]))[:DOMAIN_LIMIT]
    return result


def mapping_cost(
    graph: dict,
    mapping: dict[str, str | None],
    by_pair: dict[tuple[str, str], list[dict]],
    similarity: Callable[[str, str], float],
    *,
    partial: bool,
) -> tuple[float, float, float]:
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    node_sum = 0.0
    for node in graph["nodes"]:
        if node["id"] not in mapping:
            continue
        image = mapping[node["id"]]
        node_sum += (
            NULL_COST
            if image is None
            else (0.0 if node["label"] == "?" else label_distance(node["label"], image))
        )
    node_cost = node_sum / len(graph["nodes"])
    edge_sum = 0.0
    for edge in graph["edges"]:
        if edge["source"] not in mapping or edge["target"] not in mapping:
            if partial:
                continue
            edge_sum += 1.0
            continue
        source, target = mapping[edge["source"]], mapping[edge["target"]]
        if source is None or target is None:
            edge_sum += 1.0
            continue
        query_text = query_edge_text(edge, labels)
        best = max(
            (
                similarity(query_text, edge_text(a["source"], a["relation"], a["target"]))
                for a in by_pair.get((source, target), [])
            ),
            default=0.0,
        )
        edge_sum += 1.0 - best
    edge_cost = edge_sum / len(graph["edges"]) if graph["edges"] else 0.0
    return NODE_WEIGHT * node_cost + EDGE_WEIGHT * edge_cost, node_cost, edge_cost


def soft_search(
    graph: dict,
    domains: dict[str, list[str]],
    arcs: list[dict],
    similarity: Callable[[str, str], float],
) -> list[dict]:
    _, _, by_pair = indices(arcs)
    degree = {node["id"]: 0 for node in graph["nodes"]}
    for edge in graph["edges"]:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    order = sorted(degree, key=lambda node_id: (-degree[node_id], node_id))
    required = max(1, math.ceil(0.8 * len(order)))
    beam: list[dict[str, str | None]] = [{}]
    for depth, node_id in enumerate(order):
        expanded = []
        for state in beam:
            used = {value for value in state.values() if value is not None}
            for image in [*domains.get(node_id, []), None]:
                if image is not None and image in used:
                    continue
                candidate = {**state, node_id: image}
                possible = (
                    sum(value is not None for value in candidate.values()) + len(order) - depth - 1
                )
                if possible < required:
                    continue
                cost, _, _ = mapping_cost(graph, candidate, by_pair, similarity, partial=True)
                expanded.append((cost, candidate))
        expanded.sort(
            key=lambda item: (
                item[0],
                tuple("~" if v is None else v for _, v in sorted(item[1].items())),
            )
        )
        beam = [state for _, state in expanded[:BEAM_WIDTH]]
        if not beam:
            return []
    results = []
    for mapping in beam:
        cost, node_cost, edge_cost = mapping_cost(
            graph, mapping, by_pair, similarity, partial=False
        )
        results.append(
            {
                "mapping": mapping,
                "cost": cost,
                "node_cost": node_cost,
                "edge_cost": edge_cost,
            }
        )
    return sorted(
        results,
        key=lambda row: (
            row["cost"],
            tuple("~" if v is None else v for _, v in sorted(row["mapping"].items())),
        ),
    )[:TOP_K]


def mapping_evidence(
    graph: dict,
    mapping: dict[str, str | None],
    arcs: list[dict],
    similarity: Callable[[str, str], float],
) -> list[dict]:
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    _, _, by_pair = indices(arcs)
    evidence = []
    for edge in graph["edges"]:
        source, target = mapping[edge["source"]], mapping[edge["target"]]
        if source is None or target is None:
            continue
        query_text = query_edge_text(edge, labels)
        choices = by_pair.get((source, target), [])
        if not choices:
            continue
        best = max(
            choices,
            key=lambda arc: (
                similarity(query_text, edge_text(arc["source"], arc["relation"], arc["target"])),
                arc["relation"],
            ),
        )
        if best["evidence"] not in evidence:
            evidence.append(best["evidence"])
    return evidence[:20]


def score_row(
    row: dict, b4: dict, encoder: OnnxRelationEncoder, *, fixed_only: bool = False
) -> dict:
    graph = row["graph"]
    arcs = directed_arcs(row.get("pool_triples", []))
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    if fixed_only:
        allowed_pairs = {
            (source, target)
            for edge in graph["edges"]
            for source in row.get("candidate_ids", {}).get(edge["source"], [])
            for target in row.get("candidate_ids", {}).get(edge["target"], [])
        }
        scored_arcs = [arc for arc in arcs if (arc["source"], arc["target"]) in allowed_pairs]
    else:
        scored_arcs = arcs
    texts = {
        *(query_edge_text(edge, labels) for edge in graph["edges"]),
        *(edge_text(arc["source"], arc["relation"], arc["target"]) for arc in scored_arcs),
    }
    encoder.encode_many(texts)
    similarity = encoder.similarity
    initial = {node: list(values) for node, values in row.get("candidate_ids", {}).items()}
    fixed = soft_search(graph, initial, arcs, similarity) if graph["edges"] else []
    expanded_domains = initial if fixed_only else expand_domains(graph, initial, arcs, similarity)
    expanded = (
        fixed
        if fixed_only
        else (soft_search(graph, expanded_domains, arcs, similarity) if graph["edges"] else [])
    )
    c7 = fixed[0] if fixed else {"mapping": {}, "cost": None}
    h7 = expanded[0] if expanded else {"mapping": {}, "cost": None}
    return {
        "id": row["id"],
        "text": row["text"],
        "graph": graph,
        "arms": {
            "B1": {"evidence": row.get("b1_evidence", [])},
            "B4": b4["arms"]["B4"],
            "C7": {
                **c7,
                "evidence": mapping_evidence(graph, c7["mapping"], arcs, similarity)
                if fixed
                else [],
            },
            "H7": {
                **h7,
                "evidence": mapping_evidence(graph, h7["mapping"], arcs, similarity)
                if expanded
                else [],
            },
        },
        "initial_domain_sizes": {node: len(values) for node, values in initial.items()},
        "expanded_domain_sizes": {node: len(values) for node, values in expanded_domains.items()},
    }


def score(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.candidate_file)
    b4 = {row["id"]: row for row in read_jsonl(args.b4_file)}
    encoder = OnnxRelationEncoder()
    results = []
    for row in rows:
        results.append(score_row(row, b4[row["id"]], encoder, fixed_only=args.fixed_only))
        print(f"scored {len(results)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.out_dir / "retrieval.jsonl", results)


def evaluate(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry for claim, entry in raw.items()}
    totals = {arm: [0, 0] for arm in ARMS}
    audits = []
    for row in rows:
        entry = gold[row["id"]]
        details = {}
        for arm in ARMS:
            evidence = row["arms"][arm]["evidence"]
            covered = total = 0
            if entry["Label"][0]:
                for start, paths in entry.get("Evidence", {}).items():
                    for path in paths:
                        total += 1
                        covered += has_annotated_path(start, path, evidence)
            totals[arm][0] += covered
            totals[arm][1] += total
            details[arm] = {"evidence": len(evidence), "covered": covered, "total": total}
        audits.append(
            {
                "id": row["id"],
                "text": row["text"],
                "mapping_changed": row["arms"]["C7"].get("mapping")
                != row["arms"]["H7"].get("mapping"),
                "arms": details,
            }
        )
    summary = {
        "split": args.split,
        "claims": len(rows),
        "mapping_changes_c7_h7": sum(row["mapping_changed"] for row in audits),
        "arms": {
            arm: {
                "nonempty_evidence": sum(bool(row["arms"][arm]["evidence"]) for row in rows),
                "covered_paths": totals[arm][0],
                "total_paths": totals[arm][1],
                "path_coverage": totals[arm][0] / totals[arm][1] if totals[arm][1] else None,
            }
            for arm in ARMS
        },
    }
    write_jsonl(args.out_dir / "retrieval-audit.jsonl", audits)
    (args.out_dir / "retrieval-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def read(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}
    output = args.out_dir / "predictions.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    cache: dict[str, tuple[str, dict, float]] = {}
    reader_arms = ("B1", *READER_ARMS) if args.include_b1 else READER_ARMS
    for row in rows:
        if row["id"] in existing:
            saved = existing[row["id"]]
            if saved["model"] != args.model:
                raise ValueError(f"cached reader used a different model: {row['id']}")
            for arm in reader_arms:
                evidence = row["arms"][arm]["evidence"]
                evidence_hash = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode()
                ).hexdigest()
                if saved["arms"][arm]["evidence_sha256"] != evidence_hash:
                    raise ValueError(f"cached reader used different evidence: {row['id']} {arm}")
            continue
        record = {"id": row["id"], "gold": gold[row["id"]], "model": args.model, "arms": {}}
        for arm in reader_arms:
            evidence = row["arms"][arm]["evidence"]
            evidence_hash = hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()
            ).hexdigest()
            verdict, usage, seconds = "UNKNOWN", {}, 0.0
            if evidence:
                key = json.dumps([row["text"], evidence], sort_keys=True)
                if key not in cache:
                    raw_answer, usage, seconds = call_model(
                        args.server_url,
                        "Return one JSON object only with verdict TRUE, FALSE or UNKNOWN. "
                        "Use only the supplied KG triples. "
                        "Missing evidence alone is not proof of falsehood.",
                        "Claim: "
                        + row["text"]
                        + "\nKG triples: "
                        + json.dumps(evidence, ensure_ascii=False)
                        + '\nReturn {"verdict":"TRUE|FALSE|UNKNOWN"}.',
                        args.reader_max_tokens,
                        model=args.model,
                        api_key=api_key_for(args),
                        json_mode="object",
                    )
                    try:
                        value = json.loads(raw_answer).get("verdict")
                        verdict = value if value in ("TRUE", "FALSE", "UNKNOWN") else "UNKNOWN"
                    except (ValueError, TypeError, AttributeError):
                        verdict = "UNKNOWN"
                    cache[key] = verdict, usage, seconds
                verdict, usage, seconds = cache[key]
            record["arms"][arm] = {
                "verdict": verdict,
                "evidence_sha256": evidence_hash,
                "correct": verdict in ("TRUE", "FALSE") and (verdict == "TRUE") == gold[row["id"]],
                "usage": usage,
                "reader_seconds": seconds,
            }
        with output.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing[row["id"]] = record
        print(f"read {len(existing)}/{len(rows)} {row['id'][:12]}", flush=True)
    summary = {
        "split": args.split,
        "claims": len(rows),
        "model": args.model,
        "arms": {
            arm: {
                "accuracy": sum(row["arms"][arm]["correct"] for row in existing.values())
                / len(rows),
                "unknown": sum(
                    row["arms"][arm]["verdict"] == "UNKNOWN" for row in existing.values()
                ),
            }
            for arm in reader_arms
        },
    }
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("score", "evaluate", "read"))
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--b4-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    parser.add_argument("--fixed-only", action="store_true")
    parser.add_argument("--include-b1", action="store_true")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    {"score": score, "evaluate": evaluate, "read": read}[args.phase](args)


if __name__ == "__main__":
    main()
