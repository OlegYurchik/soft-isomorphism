"""Prepare FactKG candidate pools without obsolete B4 beam search."""

from __future__ import annotations

import argparse
import json
import pickle
import resource
import sqlite3
import time
from pathlib import Path

from factkg_e1_pilot import bm25_incident, candidate_pool, read_jsonl, write_jsonl


def reusable_rows(previous: list[dict], current: list[dict]) -> dict[str, dict]:
    current_by_id = {row["id"]: row for row in current}
    return {
        row["id"]: row
        for row in previous
        if row["id"] in current_by_id
        and row["text"] == current_by_id[row["id"]]["text"]
        and row["graph"] == current_by_id[row["id"]]["graph"]
    }


def build_pool_row(row: dict, kg: dict, index: sqlite3.Connection) -> dict:
    started = time.monotonic()
    cpu_started = time.process_time()
    graph = row["graph"]
    result = {"id": row["id"], "text": row["text"], "graph": graph}
    if not graph["nodes"] or not graph["edges"]:
        result.update(
            {
                "status": "empty_graph",
                "pool_triples": [],
                "candidate_ids": {},
                "b1_evidence": [],
            }
        )
    else:
        _, triples, candidates = candidate_pool(kg, graph, row["text"], index)
        anchors = {identifier for identifiers in candidates.values() for identifier in identifiers}
        b1 = bm25_incident(
            [triple for triple in triples if triple.source in anchors or triple.target in anchors],
            row["text"],
            limit=20,
        )
        result.update(
            {
                "status": "pool_only",
                "pool_triples": [triple.__dict__ for triple in triples],
                "candidate_ids": candidates,
                "b1_evidence": [triple.__dict__ for triple in b1],
            }
        )
    result["pool_wall_seconds"] = time.monotonic() - started
    result["pool_cpu_seconds"] = time.process_time() - cpu_started
    return result


def run(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.extract_file)
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    index = sqlite3.connect(args.name_index)
    output = args.out_dir / "candidate-pools.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    if args.reuse_from is not None and not output.exists():
        existing = reusable_rows(read_jsonl(args.reuse_from), rows)
        write_jsonl(output, [existing[row["id"]] for row in rows if row["id"] in existing])
    started = time.monotonic()
    cpu_started = time.process_time()
    reused = 0
    try:
        for row in rows:
            if row["id"] in existing:
                cached = existing[row["id"]]
                if cached["graph"] != row["graph"] or cached["text"] != row["text"]:
                    raise ValueError(
                        f"cached candidate pool has a different extraction: {row['id']}"
                    )
                reused += 1
                continue
            result = build_pool_row(row, kg, index)
            existing[result["id"]] = result
            with output.open("a") as stream:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(
                f"prepared {len(existing)}/{len(rows)} {result['id'][:12]} "
                f"pool={len(result['pool_triples'])} wall={result['pool_wall_seconds']:.2f}s",
                flush=True,
            )
    finally:
        index.close()

    summary = {
        "claims": len(rows),
        "prepared_this_run": len(rows) - reused,
        "reused": reused,
        "run_wall_seconds": time.monotonic() - started,
        "run_cpu_seconds": time.process_time() - cpu_started,
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mean_pool_triples": sum(len(row.get("pool_triples", [])) for row in existing.values())
        / len(rows),
        "mean_b1_evidence": sum(len(row.get("b1_evidence", [])) for row in existing.values())
        / len(rows),
    }
    (args.out_dir / "candidate-pools-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--reuse-from",
        type=Path,
        help="seed exact text+graph matches from an earlier candidate-pools JSONL",
    )
    parser.add_argument(
        "--kg", type=Path, default=Path("data/factkg/data/dbpedia_2015_undirected_light.pickle")
    )
    parser.add_argument(
        "--name-index", type=Path, default=Path("data/factkg/index/entities-fts.sqlite")
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
