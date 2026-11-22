"""Evaluate H10 component ablations with the frozen UNKNOWN reader protocol."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

from factkg_e1_pilot import digest, read_jsonl
from factkg_h9_edge_path import exact_paired_pvalue, macro_f1
from factkg_h11_unknown_fallback import (
    evidence_hash,
    hybrid_verdict,
    is_correct,
    load_arm_predictions,
    read_arm,
    seed_cache,
)


def metrics(records: list[dict], arm: str) -> dict:
    return {
        "accuracy": sum(row["arms"][arm]["correct"] for row in records) / len(records),
        "macro_f1": macro_f1(records, arm),
        "unknown": sum(row["arms"][arm]["verdict"] == "UNKNOWN" for row in records),
    }


def paired_summary(records: list[dict], left: str, right: str) -> dict:
    left_only = sum(
        row["arms"][left]["correct"] and not row["arms"][right]["correct"] for row in records
    )
    right_only = sum(
        row["arms"][right]["correct"] and not row["arms"][left]["correct"] for row in records
    )
    return {
        f"{left}_only_correct": left_only,
        f"{right}_only_correct": right_only,
        "net_correct": left_only - right_only,
        "exact_two_sided_p": exact_paired_pvalue(left_only, right_only),
    }


def run(args: argparse.Namespace) -> None:
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}
    b1 = load_arm_predictions(args.b1_predictions, "B1", args.model)
    full = (
        load_arm_predictions(args.full_predictions, args.full_arm, args.model)
        if args.full_predictions is not None
        else {}
    )
    unknown = {identifier for identifier, row in b1.items() if row["verdict"] == "UNKNOWN"}
    cache = seed_cache(full)
    for path in args.out_dir.glob("*-predictions.jsonl"):
        cache.update(seed_cache({row["id"]: row for row in read_jsonl(path)}))
    summary = {"split": args.split, "claims": len(b1), "fallback_claims": len(unknown), "arms": {}}

    for variant in args.variants:
        source = read_jsonl(args.retrieval_dir / f"{variant}.jsonl")
        rows = [
            {
                "id": row["id"],
                "text": row["text"],
                "arms": {variant: {"evidence": row["match"]["evidence"]}},
            }
            for row in source
        ]
        changed = (
            sum(
                evidence_hash(row["arms"][variant]["evidence"])
                != full[row["id"]]["evidence_sha256"]
                for row in rows
            )
            if full
            else None
        )
        predictions = read_arm(args, rows, gold, variant, unknown, cache)
        records = []
        for identifier, b1_row in b1.items():
            verdict = hybrid_verdict(
                b1_row["verdict"], predictions.get(identifier, {"verdict": "UNKNOWN"})["verdict"]
            )
            records.append(
                {
                    "id": identifier,
                    "gold": gold[identifier],
                    "arms": {
                        "B1": {
                            "verdict": b1_row["verdict"],
                            "correct": b1_row["correct"],
                        },
                        variant: {
                            "verdict": verdict,
                            "correct": is_correct(verdict, gold[identifier]),
                        },
                    },
                }
            )
            if full:
                reference_verdict = hybrid_verdict(
                    b1_row["verdict"],
                    full.get(identifier, {"verdict": "UNKNOWN"})["verdict"],
                )
                records[-1]["arms"][args.full_arm] = {
                    "verdict": reference_verdict,
                    "correct": is_correct(reference_verdict, gold[identifier]),
                }
        method_only = sum(
            row["arms"][variant]["correct"] and not row["arms"]["B1"]["correct"] for row in records
        )
        b1_only = sum(
            row["arms"]["B1"]["correct"] and not row["arms"][variant]["correct"] for row in records
        )
        result = {
            **metrics(records, variant),
            "changed_reader_prompts_vs_full": changed,
            "correct_over_b1": sum(row["arms"][variant]["correct"] for row in records)
            - sum(row["arms"]["B1"]["correct"] for row in records),
            "method_only_correct": method_only,
            "b1_only_correct": b1_only,
            "exact_two_sided_p": exact_paired_pvalue(method_only, b1_only),
        }
        if full:
            result["paired_vs_reference"] = {
                "reference_arm": args.full_arm,
                **paired_summary(records, args.full_arm, variant),
            }
        summary["arms"][variant] = result
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-dir", type=Path, required=True)
    parser.add_argument("--b1-predictions", type=Path, required=True)
    parser.add_argument("--full-predictions", type=Path)
    parser.add_argument("--full-arm", default="H10")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
