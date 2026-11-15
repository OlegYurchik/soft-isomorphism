"""H9 diagnostic: match one query edge to a directed KG path of length one or two."""

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
from factkg_e4_experiment import OnnxRelationEncoder, has_annotated_path
from factkg_h7_soft_matching import (
    BEAM_WIDTH,
    EDGE_WEIGHT,
    NODE_WEIGHT,
    NULL_COST,
    TOP_K,
    directed_arcs,
    edge_text,
    indices,
    query_edge_text,
)

from soft_isomorphism.matching import label_distance

MAX_PATH_LENGTH = 2
PATH_LENGTH_PENALTY = 0.1
ARMS = ("B1", "H8", "H9")
PRIMARY_ARMS = ("H8", "H9")


def path_text(path: list[dict]) -> str:
    """Verbalize a directed KG path while preserving its intermediate node."""
    if len(path) == 1:
        arc = path[0]
        return edge_text(arc["source"], arc["relation"], arc["target"])
    if len(path) != 2:
        raise ValueError("H9 supports only paths of length one or two")
    first, second = path
    if first["target"] != second["source"]:
        raise ValueError("KG path must be connected and directed")
    first_text = edge_text(first["source"], first["relation"], first["target"])
    second_text = edge_text(second["source"], second["relation"], second["target"])
    return f"first edge: {first_text}; second edge: {second_text}"


def candidate_paths(
    source: str,
    target: str,
    outgoing: dict[str, list[dict]],
    by_pair: dict[tuple[str, str], list[dict]],
) -> list[list[dict]]:
    """Enumerate deterministic simple directed paths of length one or two."""
    paths = [[arc] for arc in by_pair.get((source, target), [])]
    for first in outgoing.get(source, []):
        middle = first["target"]
        if middle in (source, target):
            continue
        for second in by_pair.get((middle, target), []):
            if first["evidence"] == second["evidence"]:
                continue
            paths.append([first, second])
    unique = {}
    for path in paths:
        key = tuple((arc["source"], arc["relation"], arc["target"]) for arc in path)
        unique[key] = path
    return [unique[key] for key in sorted(unique)]


def build_path_index(
    arcs: list[dict], allowed_pairs: set[tuple[str, str]]
) -> dict[tuple[str, str], list[list[dict]]]:
    outgoing, _, by_pair = indices(arcs)
    return {
        pair: candidate_paths(pair[0], pair[1], outgoing, by_pair) for pair in sorted(allowed_pairs)
    }


def adjusted_similarity(
    query_text: str, path: list[dict], similarity: Callable[[str, str], float]
) -> float:
    return similarity(query_text, path_text(path)) - PATH_LENGTH_PENALTY * (len(path) - 1)


def best_alignment(
    query_text: str,
    paths: list[list[dict]],
    similarity: Callable[[str, str], float],
) -> tuple[list[dict] | None, float]:
    if not paths:
        return None, 0.0
    ranked = [
        (adjusted_similarity(query_text, path, similarity), path_text(path), path) for path in paths
    ]
    score, _, path = max(ranked, key=lambda item: (item[0], -len(item[2]), item[1]))
    return path, score


def mapping_cost(
    graph: dict,
    mapping: dict[str, str | None],
    path_index: dict[tuple[str, str], list[list[dict]]],
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
        _, score = best_alignment(query_text, path_index.get((source, target), []), similarity)
        edge_sum += 1.0 - score
    edge_cost = edge_sum / len(graph["edges"]) if graph["edges"] else 0.0
    return NODE_WEIGHT * node_cost + EDGE_WEIGHT * edge_cost, node_cost, edge_cost


def soft_search(
    graph: dict,
    domains: dict[str, list[str]],
    path_index: dict[tuple[str, str], list[list[dict]]],
    similarity: Callable[[str, str], float],
) -> list[dict]:
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
                cost, _, _ = mapping_cost(graph, candidate, path_index, similarity, partial=True)
                expanded.append((cost, candidate))
        expanded.sort(
            key=lambda item: (
                item[0],
                tuple("~" if value is None else value for _, value in sorted(item[1].items())),
            )
        )
        beam = [state for _, state in expanded[:BEAM_WIDTH]]
        if not beam:
            return []

    results = []
    for mapping in beam:
        cost, node_cost, edge_cost = mapping_cost(
            graph, mapping, path_index, similarity, partial=False
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
            tuple("~" if value is None else value for _, value in sorted(row["mapping"].items())),
        ),
    )[:TOP_K]


def mapping_evidence(
    graph: dict,
    mapping: dict[str, str | None],
    path_index: dict[tuple[str, str], list[list[dict]]],
    similarity: Callable[[str, str], float],
) -> tuple[list[dict], list[dict]]:
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    evidence = []
    alignments = []
    for edge in graph["edges"]:
        source, target = mapping[edge["source"]], mapping[edge["target"]]
        if source is None or target is None:
            continue
        query_text = query_edge_text(edge, labels)
        path, score = best_alignment(query_text, path_index.get((source, target), []), similarity)
        if path is None:
            continue
        alignments.append(
            {
                "query_edge": edge,
                "kg_path_length": len(path),
                "adjusted_similarity": score,
                "kg_path": [arc["evidence"] for arc in path],
            }
        )
        for arc in path:
            if arc["evidence"] not in evidence:
                evidence.append(arc["evidence"])
    return evidence[:20], alignments


def score_row(row: dict, h8: dict, encoder: OnnxRelationEncoder) -> dict:
    graph = row["graph"]
    arcs = directed_arcs(row.get("pool_triples", []))
    domains = {node: list(values) for node, values in row.get("candidate_ids", {}).items()}
    allowed_pairs = {
        (source, target)
        for edge in graph["edges"]
        for source in domains.get(edge["source"], [])
        for target in domains.get(edge["target"], [])
    }
    path_index = build_path_index(arcs, allowed_pairs)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    texts = {
        *(query_edge_text(edge, labels) for edge in graph["edges"]),
        *(path_text(path) for paths in path_index.values() for path in paths),
    }
    encoder.encode_many(texts)
    matches = soft_search(graph, domains, path_index, encoder.similarity) if graph["edges"] else []
    best = matches[0] if matches else {"mapping": {}, "cost": None}
    evidence, alignments = (
        mapping_evidence(graph, best["mapping"], path_index, encoder.similarity)
        if matches
        else ([], [])
    )
    h8_arm = h8["arms"]["C7"]
    return {
        "id": row["id"],
        "text": row["text"],
        "graph": graph,
        "arms": {
            "B1": h8["arms"]["B1"],
            "H8": h8_arm,
            "H9": {**best, "evidence": evidence, "alignments": alignments},
        },
        "mapping_changed_h8_h9": h8_arm.get("mapping") != best.get("mapping"),
    }


def score(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.candidate_file)
    if args.row_limit is not None:
        rows = rows[: args.row_limit]
    h8 = {row["id"]: row for row in read_jsonl(args.h8_file)}
    encoder = OnnxRelationEncoder()
    results = []
    for row in rows:
        results.append(score_row(row, h8[row["id"]], encoder))
        print(f"scored {len(results)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.out_dir / "retrieval.jsonl", results)


def evaluate(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry for claim, entry in raw.items()}
    totals = {arm: defaultdict(int) for arm in ARMS}
    evidence_totals = {arm: 0 for arm in ARMS}
    audits = []
    for row in rows:
        entry = gold[row["id"]]
        details = {}
        for arm in ARMS:
            evidence = row["arms"][arm]["evidence"]
            evidence_totals[arm] += len(evidence)
            covered = total = 0
            by_length = defaultdict(lambda: [0, 0])
            if entry["Label"][0]:
                for start, paths in entry.get("Evidence", {}).items():
                    for path in paths:
                        length = len(path)
                        hit = bool(has_annotated_path(start, path, evidence))
                        total += 1
                        covered += hit
                        by_length[length][0] += hit
                        by_length[length][1] += 1
                        totals[arm][f"covered_{length}"] += hit
                        totals[arm][f"total_{length}"] += 1
            totals[arm]["covered"] += covered
            totals[arm]["total"] += total
            details[arm] = {
                "evidence": len(evidence),
                "covered": covered,
                "total": total,
                "by_length": {str(length): values for length, values in sorted(by_length.items())},
            }
        audits.append(
            {
                "id": row["id"],
                "text": row["text"],
                "mapping_changed_h8_h9": row["mapping_changed_h8_h9"],
                "arms": details,
            }
        )
    lengths = sorted(
        {
            int(key.removeprefix("total_"))
            for values in totals.values()
            for key in values
            if key.startswith("total_")
        }
    )
    summary = {
        "split": args.split,
        "claims": len(rows),
        "path_length_penalty": PATH_LENGTH_PENALTY,
        "mapping_changes_h8_h9": sum(row["mapping_changed_h8_h9"] for row in rows),
        "arms": {
            arm: {
                "nonempty_evidence": sum(bool(row["arms"][arm]["evidence"]) for row in rows),
                "mean_evidence_triples": evidence_totals[arm] / len(rows),
                "covered_paths": totals[arm]["covered"],
                "total_paths": totals[arm]["total"],
                "path_coverage": totals[arm]["covered"] / totals[arm]["total"]
                if totals[arm]["total"]
                else None,
                "coverage_by_gold_length": {
                    str(length): {
                        "covered": totals[arm][f"covered_{length}"],
                        "total": totals[arm][f"total_{length}"],
                    }
                    for length in lengths
                },
            }
            for arm in ARMS
        },
    }
    write_jsonl(args.out_dir / "retrieval-audit.jsonl", audits)
    (args.out_dir / "retrieval-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def macro_f1(records: list[dict], arm: str) -> float:
    scores = []
    for positive_verdict, gold_value in (("TRUE", True), ("FALSE", False)):
        tp = sum(
            row["gold"] == gold_value and row["arms"][arm]["verdict"] == positive_verdict
            for row in records
        )
        fp = sum(
            row["gold"] != gold_value and row["arms"][arm]["verdict"] == positive_verdict
            for row in records
        )
        fn = sum(
            row["gold"] == gold_value and row["arms"][arm]["verdict"] != positive_verdict
            for row in records
        )
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return sum(scores) / len(scores)


def exact_paired_pvalue(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(left_only, right_only) + 1))
    return min(1.0, 2 * tail / (2**discordant))


def read(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}
    output = args.out_dir / "predictions.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    cache: dict[str, tuple[str, dict, float]] = {}
    reader_arms = ARMS if args.include_b1 else PRIMARY_ARMS
    for row in rows:
        if row["id"] in existing:
            saved = existing[row["id"]]
            if saved["model"] != args.model:
                raise ValueError(f"cached reader used a different model: {row['id']}")
            for arm in reader_arms:
                evidence_hash = hashlib.sha256(
                    json.dumps(row["arms"][arm]["evidence"], sort_keys=True).encode()
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

    records = list(existing.values())
    h9_only = sum(
        row["arms"]["H9"]["correct"] and not row["arms"]["H8"]["correct"] for row in records
    )
    h8_only = sum(
        row["arms"]["H8"]["correct"] and not row["arms"]["H9"]["correct"] for row in records
    )
    summary = {
        "split": args.split,
        "claims": len(rows),
        "model": args.model,
        "arms": {
            arm: {
                "accuracy": sum(row["arms"][arm]["correct"] for row in records) / len(rows),
                "macro_f1": macro_f1(records, arm),
                "unknown": sum(row["arms"][arm]["verdict"] == "UNKNOWN" for row in records),
            }
            for arm in reader_arms
        },
        "paired_h9_h8": {
            "h9_only_correct": h9_only,
            "h8_only_correct": h8_only,
            "exact_two_sided_p": exact_paired_pvalue(h9_only, h8_only),
        },
    }
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("score", "evaluate", "read"))
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--h8-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    parser.add_argument("--include-b1", action="store_true")
    parser.add_argument("--row-limit", type=int)
    args = parser.parse_args()
    if args.row_limit is not None and args.row_limit < 1:
        parser.error("row-limit must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    {"score": score, "evaluate": evaluate, "read": read}[args.phase](args)


if __name__ == "__main__":
    main()
