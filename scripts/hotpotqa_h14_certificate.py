"""Falsification pilot for H14 certified provenance-constrained retrieval.

The v0 threat model is deliberately narrow and exact: one extracted triple may
be missing.  A radius-one certificate is issued only when the winning set of
source sentences is unchanged after deleting every individual triple.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from factkg_e4_experiment import OnnxRelationEncoder
from factkg_h7_soft_matching import directed_arcs, query_edge_text
from factkg_h9_edge_path import build_path_index, mapping_evidence, path_text, soft_search
from factkg_h10_endpoint_paths import propose_domains
from hotpotqa_graph_pilot import digest_paragraph, read_jsonl
from hotpotqa_structured_pilot import candidate_domains, evidence_from_match

from soft_isomorphism.hotpotqa import HotpotInput, load_hotpot_split, supporting_metrics

EvidenceKey = tuple[tuple[str, int], ...]


def evidence_key(evidence: list[dict]) -> EvidenceKey:
    """Identify retrieval output by source sentences, not internal graph nodes."""
    return tuple(
        sorted(
            {
                (str(item["title"]), int(item["sent_id"]))
                for item in evidence
                if item.get("title") is not None and item.get("sent_id") is not None
            }
        )
    )


def distinct_evidence_margin(candidates: list[dict]) -> float | None:
    """Return the cost gap between the two best distinct evidence sets."""
    if len(candidates) < 2:
        return None
    return float(candidates[1]["cost"] - candidates[0]["cost"])


def final_candidates(
    example: HotpotInput, candidates: list[dict], evidence_budget: int
) -> list[dict]:
    """Collapse graph mappings by the actual graph-first/BM25-filled output."""
    by_evidence: dict[EvidenceKey, dict] = {}
    for candidate in candidates:
        evidence, graph_sentences = evidence_from_match(
            example, candidate["evidence"], evidence_budget
        )
        key = evidence_key(evidence)
        if key not in by_evidence:
            by_evidence[key] = {
                **candidate,
                "graph_evidence_key": candidate["evidence_key"],
                "evidence": evidence,
                "evidence_key": key,
                "graph_sentences": graph_sentences,
            }
    return sorted(by_evidence.values(), key=lambda row: (row["cost"], row["evidence_key"]))


def certify_drop_one(base_evidence: EvidenceKey, worlds: list[dict]) -> tuple[bool, dict | None]:
    """Exact radius-one certificate and a deterministic failure witness."""
    for world in worlds:
        if world["evidence_key"] != base_evidence:
            return False, world
    return True, None


def selected_triples(
    example: HotpotInput, selected_titles: list[str], contexts: dict[str, dict]
) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for sentence in example.sentences:
        grouped.setdefault(sentence.title, []).append(sentence.text)
    triples = []
    for title in selected_titles:
        texts = grouped.get(title)
        if texts is None:
            continue
        row = contexts.get(digest_paragraph(title, texts))
        if row is not None and row["valid"]:
            triples.extend(row["triples"])
    return triples


def ranked_evidence(graph: dict, triples: list[dict], encoder: OnnxRelationEncoder) -> list[dict]:
    """Reproduce the final Hotpot matcher while retaining distinct alternatives."""
    if not graph.get("edges") or not triples:
        return []
    arcs = directed_arcs(triples)
    initial = candidate_domains(graph, triples)
    domains, penalties, _ = propose_domains(
        graph,
        initial,
        arcs,
        encoder,
        candidates_per_node=1,
        expanded_node_penalty=0.0,
        contextual_proposals=True,
    )
    allowed_pairs = {
        (source, target)
        for edge in graph["edges"]
        for source in domains.get(edge["source"], [])
        for target in domains.get(edge["target"], [])
    }
    path_index = build_path_index(arcs, allowed_pairs)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    encoder.encode_many(
        {
            *(query_edge_text(edge, labels) for edge in graph["edges"]),
            *(path_text(path) for paths in path_index.values() for path in paths),
        }
    )
    matches = soft_search(
        graph,
        domains,
        path_index,
        encoder.similarity,
        node_penalties=penalties,
    )
    by_evidence: dict[EvidenceKey, dict] = {}
    for match in matches:
        evidence, _ = mapping_evidence(graph, match["mapping"], path_index, encoder.similarity)
        key = evidence_key(evidence)
        if key not in by_evidence:
            by_evidence[key] = {
                "cost": match["cost"],
                "mapping": match["mapping"],
                "evidence": evidence,
                "evidence_key": key,
            }
    return sorted(
        by_evidence.values(),
        key=lambda row: (row["cost"], row["evidence_key"]),
    )


def mean(rows: list[dict], key: str) -> float | None:
    return sum(row[key] for row in rows) / len(rows) if rows else None


def metric_summary(rows: list[dict]) -> dict:
    return {
        "examples": len(rows),
        "support_precision": mean(rows, "support_precision"),
        "support_recall": mean(rows, "support_recall"),
        "support_f1": mean(rows, "support_f1"),
    }


def analyze_example(
    example: HotpotInput,
    graph: dict,
    triples: list[dict],
    gold_support: frozenset[tuple[str, int]],
    encoder: OnnxRelationEncoder,
    evidence_budget: int,
) -> dict | None:
    base_candidates = final_candidates(
        example, ranked_evidence(graph, triples, encoder), evidence_budget
    )
    if len(base_candidates) < 2 or not base_candidates[0]["evidence_key"]:
        return None
    best = base_candidates[0]
    worlds = []
    for index, dropped in enumerate(triples):
        candidates = final_candidates(
            example,
            ranked_evidence(graph, [*triples[:index], *triples[index + 1 :]], encoder),
            evidence_budget,
        )
        if not candidates:
            fallback, graph_sentences = evidence_from_match(example, [], evidence_budget)
            candidates = [
                {
                    "cost": None,
                    "evidence_key": evidence_key(fallback),
                    "graph_sentences": graph_sentences,
                }
            ]
        winner = candidates[0] if candidates else None
        worlds.append(
            {
                "operation": "drop_triple",
                "triple_index": index,
                "dropped_triple": dropped,
                "cost": winner["cost"] if winner is not None else None,
                "evidence_key": winner["evidence_key"] if winner is not None else (),
            }
        )
    certified, witness = certify_drop_one(best["evidence_key"], worlds)
    metrics = supporting_metrics(set(best["evidence_key"]), gold_support)
    return {
        "id": example.id,
        "question": example.question,
        "triples": len(triples),
        "base_cost": best["cost"],
        "base_margin": distinct_evidence_margin(base_candidates),
        "base_evidence": [
            {"title": title, "sent_id": sent_id} for title, sent_id in best["evidence_key"]
        ],
        "candidate_evidence_sets": len(base_candidates),
        "graph_sentences": best["graph_sentences"],
        "worlds": len(worlds),
        "stable_worlds": sum(world["evidence_key"] == best["evidence_key"] for world in worlds),
        "certified_radius": 1 if certified else 0,
        "failure_witness": witness,
        **metrics,
    }


def run(args: argparse.Namespace) -> None:
    inputs, gold = load_hotpot_split(
        args.parquet,
        args.split_file,
        args.split,
        args.scan_limit,
        args.offset,
    )
    examples = {example.id: example for example in inputs}
    queries = {row["id"]: row for row in read_jsonl(args.graph_dir / "query-extractions.jsonl")}
    contexts = {
        row["digest"]: row for row in read_jsonl(args.graph_dir / "context-extractions.jsonl")
    }
    retrieval = {
        row["id"]: row for row in read_jsonl(args.retrieval_dir / "structured-retrieval.jsonl")
    }
    encoder = OnnxRelationEncoder()
    rows = []
    scanned = 0
    for example in inputs:
        if len(rows) == args.limit:
            break
        scanned += 1
        query = queries.get(example.id)
        retrieved = retrieval.get(example.id)
        if query is None or not query["valid"] or retrieved is None:
            continue
        triples = selected_triples(example, retrieved["selected_titles"], contexts)
        result = analyze_example(
            examples[example.id],
            query["graph"],
            triples,
            gold[example.id].supporting_facts,
            encoder,
            args.evidence_budget,
        )
        if result is None:
            continue
        rows.append(result)
        print(
            f"certified {len(rows)}/{args.limit} {example.id} "
            f"r={result['certified_radius']} worlds={result['worlds']}",
            flush=True,
        )

    certified_rows = [row for row in rows if row["certified_radius"] >= 1]
    uncertified_rows = [row for row in rows if row["certified_radius"] == 0]
    margin_ranked = sorted(
        rows,
        key=lambda row: (
            -(row["base_margin"] if row["base_margin"] is not None else -math.inf),
            row["id"],
        ),
    )
    margin_control = margin_ranked[: len(certified_rows)]
    summary = {
        "hypothesis": "H14",
        "threat_model": "delete any one extracted triple",
        "split": args.split,
        "offset": args.offset,
        "scan_limit": args.scan_limit,
        "evidence_budget": args.evidence_budget,
        "scanned": scanned,
        "eligible_examples": len(rows),
        "new_llm_calls": 0,
        "certificate_soundness_against_exhaustive_worlds": 1.0,
        "certified_radius_1": len(certified_rows),
        "certified_coverage": len(certified_rows) / len(rows) if rows else 0.0,
        "all": metric_summary(rows),
        "certified": metric_summary(certified_rows),
        "uncertified": metric_summary(uncertified_rows),
        "same_coverage_margin_control": metric_summary(margin_control),
        "certificate_margin_overlap": len(
            {row["id"] for row in certified_rows} & {row["id"] for row in margin_control}
        ),
        "mean_margin_certified": mean(certified_rows, "base_margin"),
        "mean_margin_uncertified": mean(uncertified_rows, "base_margin"),
        "decision": None,
    }
    if not rows:
        summary["decision"] = "invalid: no eligible examples"
    elif summary["certified_coverage"] < 0.2:
        summary["decision"] = "stop: certified coverage below 20%"
    elif (summary["certified"]["support_f1"] or 0.0) <= (
        summary["same_coverage_margin_control"]["support_f1"] or 0.0
    ):
        summary["decision"] = "stop: certificate does not beat raw margin at equal coverage"
    else:
        summary["decision"] = "go: extend the threat model and validate on a held-out split"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "certificate.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--split", choices=("development", "evaluation"), default="evaluation")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--scan-limit", type=int, default=500)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--evidence-budget", type=int, default=5)
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=Path("data/evaluation/hotpotqa-evaluation-500-graph"),
    )
    parser.add_argument(
        "--retrieval-dir",
        type=Path,
        default=Path("data/evaluation/hotpotqa-evaluation-500-graph-aware"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/evaluation/h14-certified-soft-matching-pilot"),
    )
    args = parser.parse_args()
    if (
        args.limit < 1
        or args.evidence_budget < 1
        or args.scan_limit < args.limit
        or args.offset < 0
    ):
        parser.error("require positive limit, scan-limit >= limit, and non-negative offset")
    run(args)


if __name__ == "__main__":
    main()
