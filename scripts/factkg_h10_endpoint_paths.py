"""H10 diagnostic: path-guided endpoint linking followed by H9 soft matching."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Callable

from factkg_e1_pilot import api_key_for, call_model, digest, read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder, has_annotated_path, relation_text
from factkg_h7_soft_matching import directed_arcs, indices
from factkg_h9_edge_path import (
    build_path_index,
    exact_paired_pvalue,
    macro_f1,
    mapping_evidence,
    path_text,
    query_edge_text,
    soft_search,
)

from soft_isomorphism.matching import label_distance

NEW_CANDIDATES_PER_NODE = 2
PROPOSAL_RELATION_WEIGHT = 0.7
PROPOSAL_LABEL_WEIGHT = 0.3
PROPOSAL_LENGTH_PENALTY = 0.1
EXPANDED_NODE_PENALTY = 0.15
ARMS = ("B1", "H8", "H9", "H10")


def relation_sequence_text(path: list[dict]) -> str:
    parts = []
    for arc in path:
        relation = arc["relation"]
        readable = relation_text(relation)
        if relation.startswith("~"):
            readable = "inverse " + readable
        parts.append(readable)
    return " then ".join(parts)


def forward_paths(anchor: str, outgoing: dict[str, list[dict]]) -> Iterator[list[dict]]:
    for first in outgoing.get(anchor, []):
        yield [first]
        middle = first["target"]
        if middle == anchor:
            continue
        for second in outgoing.get(middle, []):
            if second["target"] in (anchor, middle) or first["evidence"] == second["evidence"]:
                continue
            yield [first, second]


def backward_paths(anchor: str, incoming: dict[str, list[dict]]) -> Iterator[list[dict]]:
    for second in incoming.get(anchor, []):
        yield [second]
        middle = second["source"]
        if middle == anchor:
            continue
        for first in incoming.get(middle, []):
            if first["source"] in (anchor, middle) or first["evidence"] == second["evidence"]:
                continue
            yield [first, second]


def raw_proposals(
    graph: dict,
    initial: dict[str, list[str]],
    outgoing: dict[str, list[dict]],
    incoming: dict[str, list[dict]],
) -> Iterator[dict]:
    for edge_index, edge in enumerate(graph["edges"]):
        for anchor in initial.get(edge["source"], []):
            for path in forward_paths(anchor, outgoing):
                yield {
                    "node": edge["target"],
                    "candidate": path[-1]["target"],
                    "edge_index": edge_index,
                    "anchor": anchor,
                    "direction": "forward",
                    "path": path,
                }
        for anchor in initial.get(edge["target"], []):
            for path in backward_paths(anchor, incoming):
                yield {
                    "node": edge["source"],
                    "candidate": path[0]["source"],
                    "edge_index": edge_index,
                    "anchor": anchor,
                    "direction": "backward",
                    "path": path,
                }


def proposal_score(
    query_relation: str,
    query_label: str,
    candidate: str,
    path: list[dict],
    similarity: Callable[[str, str], float],
) -> float:
    relation_score = similarity(query_relation, relation_sequence_text(path))
    label_score = 0.0 if query_label == "?" else 1.0 - label_distance(query_label, candidate)
    return (
        PROPOSAL_RELATION_WEIGHT * relation_score
        + PROPOSAL_LABEL_WEIGHT * label_score
        - PROPOSAL_LENGTH_PENALTY * (len(path) - 1)
    )


def propose_domains(
    graph: dict,
    initial: dict[str, list[str]],
    arcs: list[dict],
    encoder: OnnxRelationEncoder,
) -> tuple[dict[str, list[str]], dict[tuple[str, str], float], list[dict]]:
    outgoing, incoming, _ = indices(arcs)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    relation_queries = [relation_text(edge["relation"]) for edge in graph["edges"]]
    relation_sequences = {
        relation_sequence_text(proposal["path"])
        for proposal in raw_proposals(graph, initial, outgoing, incoming)
    }
    encoder.encode_many({*relation_queries, *relation_sequences})

    best: dict[tuple[str, str], dict] = {}
    for proposal in raw_proposals(graph, initial, outgoing, incoming):
        node_id, candidate = proposal["node"], proposal["candidate"]
        if candidate in initial.get(node_id, []):
            continue
        edge = graph["edges"][proposal["edge_index"]]
        score = proposal_score(
            relation_queries[proposal["edge_index"]],
            labels[node_id],
            candidate,
            proposal["path"],
            encoder.similarity,
        )
        record = {
            **proposal,
            "score": score,
            "relation_sequence": relation_sequence_text(proposal["path"]),
            "path_evidence": [arc["evidence"] for arc in proposal["path"]],
            "query_edge": edge,
        }
        key = (node_id, candidate)
        current = best.get(key)
        record_key = (
            record["score"],
            -len(record["path"]),
            record["relation_sequence"],
            record["anchor"],
        )
        if current is None:
            best[key] = record
            continue
        current_key = (
            current["score"],
            -len(current["path"]),
            current["relation_sequence"],
            current["anchor"],
        )
        if record_key > current_key:
            best[key] = record

    selected = []
    for node_id in sorted(labels):
        choices = [record for (node, _), record in best.items() if node == node_id]
        choices.sort(key=lambda record: (-record["score"], record["candidate"]))
        selected.extend(choices[:NEW_CANDIDATES_PER_NODE])

    expanded = {node: list(values) for node, values in initial.items()}
    penalties = {}
    for record in selected:
        node_id, candidate = record["node"], record["candidate"]
        expanded.setdefault(node_id, []).append(candidate)
        penalties[node_id, candidate] = EXPANDED_NODE_PENALTY
        record.pop("path")
    return expanded, penalties, selected


def score_row(row: dict, h9: dict, encoder: OnnxRelationEncoder) -> dict:
    graph = row["graph"]
    arcs = directed_arcs(row.get("pool_triples", []))
    initial = {node: list(values) for node, values in row.get("candidate_ids", {}).items()}
    expanded, penalties, proposals = propose_domains(graph, initial, arcs, encoder)
    allowed_pairs = {
        (source, target)
        for edge in graph["edges"]
        for source in expanded.get(edge["source"], [])
        for target in expanded.get(edge["target"], [])
    }
    path_index = build_path_index(arcs, allowed_pairs)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    encoder.encode_many(
        {
            *(query_edge_text(edge, labels) for edge in graph["edges"]),
            *(path_text(path) for paths in path_index.values() for path in paths),
        }
    )
    matches = (
        soft_search(
            graph,
            expanded,
            path_index,
            encoder.similarity,
            node_penalties=penalties,
        )
        if graph["edges"]
        else []
    )
    best = matches[0] if matches else {"mapping": {}, "cost": None}
    evidence, alignments = (
        mapping_evidence(graph, best["mapping"], path_index, encoder.similarity)
        if matches
        else ([], [])
    )
    used_expanded = sorted(
        node_id
        for node_id, image in best["mapping"].items()
        if image is not None and (node_id, image) in penalties
    )
    return {
        "id": row["id"],
        "text": row["text"],
        "graph": graph,
        "arms": {
            "B1": h9["arms"]["B1"],
            "H8": h9["arms"]["H8"],
            "H9": h9["arms"]["H9"],
            "H10": {**best, "evidence": evidence, "alignments": alignments},
        },
        "proposals": proposals,
        "used_expanded_nodes": used_expanded,
        "mapping_changed_h9_h10": h9["arms"]["H9"].get("mapping") != best.get("mapping"),
    }


def score(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.candidate_file)
    if args.row_limit is not None:
        rows = rows[: args.row_limit]
    h9 = {row["id"]: row for row in read_jsonl(args.h9_file)}
    encoder = OnnxRelationEncoder()
    results = []
    for row in rows:
        results.append(score_row(row, h9[row["id"]], encoder))
        print(f"scored {len(results)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.out_dir / "retrieval.jsonl", results)


def evaluate(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry for claim, entry in raw.items()}
    totals = {arm: defaultdict(int) for arm in ARMS}
    evidence_totals = {arm: 0 for arm in ARMS}
    h10_only = h9_only = 0
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
        if entry["Label"][0]:
            for start, paths in entry.get("Evidence", {}).items():
                for path in paths:
                    h9_hit = bool(has_annotated_path(start, path, row["arms"]["H9"]["evidence"]))
                    h10_hit = bool(has_annotated_path(start, path, row["arms"]["H10"]["evidence"]))
                    h10_only += h10_hit and not h9_hit
                    h9_only += h9_hit and not h10_hit
        audits.append(
            {
                "id": row["id"],
                "text": row["text"],
                "mapping_changed_h9_h10": row["mapping_changed_h9_h10"],
                "used_expanded_nodes": row["used_expanded_nodes"],
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
        "parameters": {
            "new_candidates_per_node": NEW_CANDIDATES_PER_NODE,
            "proposal_relation_weight": PROPOSAL_RELATION_WEIGHT,
            "proposal_label_weight": PROPOSAL_LABEL_WEIGHT,
            "proposal_length_penalty": PROPOSAL_LENGTH_PENALTY,
            "expanded_node_penalty": EXPANDED_NODE_PENALTY,
        },
        "mapping_changes_h9_h10": sum(row["mapping_changed_h9_h10"] for row in rows),
        "claims_using_expanded_endpoint": sum(bool(row["used_expanded_nodes"]) for row in rows),
        "path_coverage_pairing": {
            "h10_only_covered_paths": h10_only,
            "h9_only_covered_paths": h9_only,
        },
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


def read(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}
    output = args.out_dir / "predictions.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    cache: dict[str, tuple[str, dict, float]] = {}
    reader_arms = ("B1", "H9", "H10") if args.include_b1 else ("H9", "H10")
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

    records = [existing[row["id"]] for row in rows]
    h10_only = sum(
        row["arms"]["H10"]["correct"] and not row["arms"]["H9"]["correct"] for row in records
    )
    h9_only = sum(
        row["arms"]["H9"]["correct"] and not row["arms"]["H10"]["correct"] for row in records
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
        "paired_h10_h9": {
            "h10_only_correct": h10_only,
            "h9_only_correct": h9_only,
            "exact_two_sided_p": exact_paired_pvalue(h10_only, h9_only),
        },
    }
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("score", "evaluate", "read"))
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--h9-file", type=Path, required=True)
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
