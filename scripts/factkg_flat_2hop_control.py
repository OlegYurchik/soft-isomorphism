"""Flat two-hop evidence control without graph mapping or path constraints."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from collections.abc import Callable
from pathlib import Path

from factkg_e1_pilot import read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder
from factkg_h7_soft_matching import edge_text
from factkg_h11_lazy_retrieval import unknown_ids

VARIANT = "flat-2hop"


def triple_key(triple: dict) -> tuple[str, str, str]:
    return triple["source"], triple["relation"], triple["target"]


def triple_text(triple: dict) -> str:
    return edge_text(triple["source"], triple["relation"], triple["target"])


def rank_flat_evidence(
    claim: str,
    pool_triples: list[dict],
    budget: int,
    similarity: Callable[[str, str], float],
) -> tuple[list[dict], list[dict]]:
    """Rank unique real KG triples independently by claim-to-triple similarity."""
    if budget < 0:
        raise ValueError("evidence budget must be non-negative")
    unique = {triple_key(triple): triple for triple in pool_triples}
    ranked = sorted(
        (
            {
                "triple": unique[key],
                "similarity": similarity(claim, triple_text(unique[key])),
            }
            for key in sorted(unique)
        ),
        key=lambda item: (-item["similarity"], triple_key(item["triple"])),
    )
    selected = ranked[:budget]
    return [item["triple"] for item in selected], selected


def score_row(
    row: dict,
    budget: int,
    encoder: OnnxRelationEncoder,
) -> dict:
    started = time.monotonic()
    cpu_started = time.process_time()
    texts = {row["text"], *(triple_text(triple) for triple in row.get("pool_triples", []))}
    encoder.encode_many(texts)
    evidence, selected = rank_flat_evidence(
        row["text"],
        row.get("pool_triples", []),
        budget,
        encoder.similarity,
    )
    return {
        "id": row["id"],
        "text": row["text"],
        "variant": VARIANT,
        "evidence_budget": budget,
        "pool_triples": len({triple_key(item) for item in row.get("pool_triples", [])}),
        "retrieval_wall_seconds": time.monotonic() - started,
        "retrieval_cpu_seconds": time.process_time() - cpu_started,
        "match": {
            "evidence": evidence,
            "selected": selected,
        },
    }


def input_digest(row: dict, budget: int) -> str:
    payload = json.dumps(
        [row["text"], row.get("pool_triples", []), budget],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def load_budgets(path: Path) -> dict[str, int]:
    rows = read_jsonl(path)
    budgets = {}
    for row in rows:
        if row.get("variant") != "lean":
            raise ValueError(f"budget reference is not H10-lean: {row.get('id')}")
        budgets[row["id"]] = len(row["match"]["evidence"])
    return budgets


def run(args: argparse.Namespace) -> None:
    selected_ids = unknown_ids(args.b1_predictions, args.model)
    budgets = load_budgets(args.budget_reference)
    rows = [row for row in read_jsonl(args.candidate_file) if row["id"] in selected_ids]
    row_ids = {row["id"] for row in rows}
    if row_ids != selected_ids:
        raise ValueError(
            f"candidate file is missing {len(selected_ids - row_ids)} B1 UNKNOWN claims"
        )
    if not selected_ids <= budgets.keys():
        raise ValueError(f"budget reference is missing {len(selected_ids - budgets.keys())} claims")

    output_file = args.out_dir / f"{VARIANT}.jsonl"
    cached = {row["id"]: row for row in read_jsonl(output_file)} if output_file.exists() else {}
    valid_cached = {
        row["id"]: cached[row["id"]]
        for row in rows
        if row["id"] in cached
        and cached[row["id"]].get("input_sha256") == input_digest(row, budgets[row["id"]])
    }
    write_jsonl(output_file, valid_cached.values())
    pending = [row for row in rows if row["id"] not in valid_cached]
    encoder = OnnxRelationEncoder() if pending else None
    started = time.monotonic()
    cpu_started = time.process_time()
    output_by_id = dict(valid_cached)
    for row in pending:
        result = score_row(row, budgets[row["id"]], encoder)
        result["input_sha256"] = input_digest(row, budgets[row["id"]])
        with output_file.open("a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        output_by_id[row["id"]] = result
        print(f"scored {len(output_by_id)}/{len(rows)} {row['id'][:12]}", flush=True)
    output = [output_by_id[row["id"]] for row in rows]
    write_jsonl(output_file, output)
    seconds = time.monotonic() - started
    summary = {
        "variant": VARIANT,
        "claims": len(output),
        "run_wall_seconds": seconds,
        "run_cpu_seconds": time.process_time() - cpu_started,
        "retrieval_wall_seconds": sum(row.get("retrieval_wall_seconds", 0.0) for row in output),
        "retrieval_cpu_seconds": sum(row.get("retrieval_cpu_seconds", 0.0) for row in output),
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "processed_this_run": len(pending),
        "reused_from_cache": len(valid_cached),
        "ranking": "MiniLM cosine between the full claim and each full KG triple",
        "budget": "per-claim evidence count copied from frozen H10-lean",
        "uses_query_graph": False,
        "uses_endpoint_proposals": False,
        "uses_joint_mapping": False,
        "uses_beam_search": False,
        "mean_pool_triples": sum(row["pool_triples"] for row in output) / len(output)
        if output
        else 0.0,
        "mean_evidence": sum(len(row["match"]["evidence"]) for row in output) / len(output)
        if output
        else 0.0,
        "empty_evidence": sum(not row["match"]["evidence"] for row in output),
    }
    (args.out_dir / f"{VARIANT}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--b1-predictions", type=Path, required=True)
    parser.add_argument("--budget-reference", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
