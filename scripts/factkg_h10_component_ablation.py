"""Component ablations for the H10 matcher on B1 UNKNOWN claims."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from factkg_e1_pilot import read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder
from factkg_h10_endpoint_paths import independent_edge_match, match_row
from factkg_h11_lazy_retrieval import unknown_ids

VARIANTS = {
    "full": {},
    "one-hop-proposals": {"max_proposal_path_length": 1},
    "one-candidate": {"candidates_per_node": 1},
    "no-candidate-penalty": {"expanded_node_penalty": 0.0},
    "direct-alignments": {"max_alignment_path_length": 1},
    "lean": {"candidates_per_node": 1, "expanded_node_penalty": 0.0},
    "lean-one-hop": {
        "max_proposal_path_length": 1,
        "candidates_per_node": 1,
        "expanded_node_penalty": 0.0,
    },
    "minimal": {
        "max_proposal_path_length": 1,
        "candidates_per_node": 1,
        "expanded_node_penalty": 0.0,
        "max_alignment_path_length": 1,
    },
    "independent-edges": None,
}


def arm_row(row: dict, variant: str, encoder: OnnxRelationEncoder) -> dict:
    result = (
        independent_edge_match(row, encoder)
        if variant == "independent-edges"
        else match_row(row, encoder, **VARIANTS[variant])
    )
    return {"id": row["id"], "text": row["text"], "variant": variant, **result}


def comparison(rows: list[dict], full: dict[str, dict]) -> dict:
    return {
        "claims": len(rows),
        "mapping_changes": sum(
            row["match"].get("mapping") != full[row["id"]]["match"].get("mapping") for row in rows
        ),
        "evidence_changes": sum(
            row["match"]["evidence"] != full[row["id"]]["match"]["evidence"] for row in rows
        ),
        "empty_evidence": sum(not row["match"]["evidence"] for row in rows),
        "mean_evidence": sum(len(row["match"]["evidence"]) for row in rows) / len(rows),
        "mean_proposals": sum(len(row["proposals"]) for row in rows) / len(rows),
    }


def run(args: argparse.Namespace) -> None:
    selected = unknown_ids(args.b1_predictions, args.model)
    rows = [row for row in read_jsonl(args.candidate_file) if row["id"] in selected]
    if {row["id"] for row in rows} != selected:
        raise ValueError("candidate file does not contain every B1 UNKNOWN claim")
    encoder = OnnxRelationEncoder()
    outputs: dict[str, list[dict]] = {}
    seconds = {}
    for variant in args.variants:
        started = time.monotonic()
        outputs[variant] = [arm_row(row, variant, encoder) for row in rows]
        seconds[variant] = time.monotonic() - started
        write_jsonl(args.out_dir / f"{variant}.jsonl", outputs[variant])
        print(f"{variant}: {len(rows)} claims in {seconds[variant]:.2f}s", flush=True)

    full_rows = outputs.get("full")
    if full_rows is None and args.full_reference is not None:
        full_rows = [
            {
                "id": row["id"],
                "match": row["arms"]["H10"],
                "proposals": row["proposals"],
                "used_expanded_nodes": row["used_expanded_nodes"],
            }
            for row in read_jsonl(args.full_reference)
            if row["id"] in selected
        ]
    if full_rows is None:
        full_rows = read_jsonl(args.out_dir / "full.jsonl")
    full = {row["id"]: row for row in full_rows}
    summary = {
        "claims": len(rows),
        "variants": {
            variant: {"seconds": seconds[variant], **comparison(result, full)}
            for variant, result in outputs.items()
        },
    }
    (args.out_dir / "structural-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--b1-predictions", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--full-reference", type=Path)
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
