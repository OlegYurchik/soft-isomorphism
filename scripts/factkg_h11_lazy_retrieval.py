"""Run H11 graph retrieval only for claims where the B1 reader abstained."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from factkg_e1_pilot import read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder, rerank_row
from factkg_h7_soft_matching import score_row as h8_score_row
from factkg_h9_edge_path import score_row as h9_score_row
from factkg_h10_endpoint_paths import score_row as h10_score_row
from factkg_h11_unknown_fallback import load_arm_predictions


def unknown_ids(prediction_file: Path, model: str) -> set[str]:
    predictions = load_arm_predictions(prediction_file, "B1", model)
    return {identifier for identifier, row in predictions.items() if row["verdict"] == "UNKNOWN"}


def compare_reference(name: str, rows: list[dict], path: Path | None) -> dict | None:
    if path is None:
        return None
    reference = {row["id"]: row for row in read_jsonl(path)}
    missing = [row["id"] for row in rows if row["id"] not in reference]
    mismatches = [row["id"] for row in rows if reference.get(row["id"]) != row]
    result = {
        "rows": len(rows),
        "exact_matches": len(rows) - len(mismatches),
        "missing": missing,
        "mismatches": mismatches,
    }
    if missing or mismatches:
        raise AssertionError(f"{name} differs from reference: {result}")
    return result


def run(args: argparse.Namespace) -> None:
    started = time.monotonic()
    selected = unknown_ids(args.b1_predictions, args.model)
    source_rows = read_jsonl(args.candidate_file)
    rows = [row for row in source_rows if row["id"] in selected]
    found = {row["id"] for row in rows}
    if found != selected:
        raise ValueError(f"candidate file is missing {len(selected - found)} UNKNOWN claims")

    encoder = OnnxRelationEncoder()
    encoder.encode_many(
        {
            relation
            for row in rows
            for relation in (
                [edge["relation"] for edge in row["graph"]["edges"]]
                + [triple["relation"] for triple in row.get("pool_triples", [])]
            )
        }
    )
    b4_rows = [rerank_row(row, encoder.similarity) for row in rows]
    print(f"B4 {len(b4_rows)}/{len(source_rows)} claims", flush=True)

    h8_rows = [
        h8_score_row(row, b4, encoder, fixed_only=True)
        for row, b4 in zip(rows, b4_rows, strict=True)
    ]
    print(f"H8 {len(h8_rows)}/{len(source_rows)} claims", flush=True)

    h9_rows = [h9_score_row(row, h8, encoder) for row, h8 in zip(rows, h8_rows, strict=True)]
    print(f"H9 {len(h9_rows)}/{len(source_rows)} claims", flush=True)

    h10_rows = [h10_score_row(row, h9, encoder) for row, h9 in zip(rows, h9_rows, strict=True)]
    print(f"H10 {len(h10_rows)}/{len(source_rows)} claims", flush=True)

    outputs = {"b4": b4_rows, "h8": h8_rows, "h9": h9_rows, "h10": h10_rows}
    for name, result_rows in outputs.items():
        write_jsonl(args.out_dir / f"{name}.jsonl", result_rows)

    references = {
        name: compare_reference(name, outputs[name], getattr(args, f"reference_{name}"))
        for name in outputs
    }
    summary = {
        "source_claims": len(source_rows),
        "fallback_claims": len(rows),
        "fallback_rate": len(rows) / len(source_rows),
        "skipped_graph_retrieval_claims": len(source_rows) - len(rows),
        "skipped_graph_retrieval_rate": 1.0 - len(rows) / len(source_rows),
        "elapsed_seconds": time.monotonic() - started,
        "references": {name: value for name, value in references.items() if value is not None},
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--b1-predictions", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    for name in ("b4", "h8", "h9", "h10"):
        parser.add_argument(f"--reference-{name}", type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
