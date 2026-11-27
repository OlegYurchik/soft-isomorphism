"""H11 confirmatory reader: use graph arms only after a B1 UNKNOWN verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

from factkg_e1_pilot import api_key_for, call_model, digest, read_jsonl
from factkg_h9_edge_path import exact_paired_pvalue, macro_f1

ARMS = ("B1", "H8", "H9", "H10")
FALLBACK_ARMS = ("H8", "H9", "H10")


def evidence_hash(evidence: list[dict]) -> str:
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def parse_verdict(raw_answer: str) -> str:
    try:
        value = json.loads(raw_answer).get("verdict")
    except (ValueError, TypeError, AttributeError):
        return "UNKNOWN"
    return value if value in ("TRUE", "FALSE", "UNKNOWN") else "UNKNOWN"


def is_correct(verdict: str, gold: bool) -> bool:
    return verdict in ("TRUE", "FALSE") and (verdict == "TRUE") == gold


def hybrid_verdict(b1_verdict: str, fallback_verdict: str) -> str:
    return fallback_verdict if b1_verdict == "UNKNOWN" else b1_verdict


def load_arm_predictions(path: Path, arm: str, model: str) -> dict[str, dict]:
    rows = {row["id"]: row for row in read_jsonl(path)} if path.exists() else {}
    for row in rows.values():
        if row["arm"] != arm or row["model"] != model:
            raise ValueError(f"cached prediction has different arm or model: {row['id']}")
    return rows


def read_arm(
    args: argparse.Namespace,
    rows: list[dict],
    gold: dict[str, bool],
    arm: str,
    eligible_ids: set[str],
    cache: dict[tuple[str, str], tuple[str, dict, float]],
) -> dict[str, dict]:
    output = args.out_dir / f"{arm.lower()}-predictions.jsonl"
    existing = load_arm_predictions(output, arm, args.model)
    key = api_key_for(args)
    for row in rows:
        if row["id"] not in eligible_ids:
            continue
        evidence = row["arms"][arm]["evidence"]
        sha256 = evidence_hash(evidence)
        if row["id"] in existing:
            if existing[row["id"]]["evidence_sha256"] != sha256:
                raise ValueError(f"cached prediction used different evidence: {row['id']} {arm}")
            cached = existing[row["id"]]
            cache[(row["id"], sha256)] = (
                cached["verdict"],
                cached.get("usage", {}),
                cached.get("reader_seconds", 0.0),
            )
            continue
        verdict, usage, seconds = "UNKNOWN", {}, 0.0
        cache_key = (row["id"], sha256)
        if evidence:
            if cache_key not in cache:
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
                    api_key=key,
                    json_mode="object",
                )
                cache[cache_key] = parse_verdict(raw_answer), usage, seconds
            verdict, usage, seconds = cache[cache_key]
        record = {
            "id": row["id"],
            "arm": arm,
            "model": args.model,
            "gold": gold[row["id"]],
            "verdict": verdict,
            "correct": is_correct(verdict, gold[row["id"]]),
            "evidence_sha256": sha256,
            "usage": usage,
            "reader_seconds": seconds,
        }
        with output.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing[row["id"]] = record
        print(f"read {arm} {len(existing)}/{len(eligible_ids)} {row['id'][:12]}", flush=True)
    return existing


def arm_metrics(records: list[dict], arm: str) -> dict:
    return {
        "accuracy": sum(row["arms"][arm]["correct"] for row in records) / len(records),
        "macro_f1": macro_f1(records, arm),
        "unknown": sum(row["arms"][arm]["verdict"] == "UNKNOWN" for row in records),
    }


def b1_rows(candidate_file: Path) -> list[dict]:
    """Adapt candidate pools to the reader format without graph scoring."""
    return [
        {
            "id": row["id"],
            "text": row["text"],
            "arms": {"B1": {"evidence": row.get("b1_evidence", [])}},
        }
        for row in read_jsonl(candidate_file)
    ]


def seed_cache(predictions: dict[str, dict]) -> dict[tuple[str, str], tuple[str, dict, float]]:
    return {
        (identifier, row["evidence_sha256"]): (
            row["verdict"],
            row.get("usage", {}),
            row.get("reader_seconds", 0.0),
        )
        for identifier, row in predictions.items()
    }


def read(args: argparse.Namespace) -> None:
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}

    if args.phase in ("all", "b1"):
        rows = (
            b1_rows(args.candidate_file) if args.phase == "b1" else read_jsonl(args.retrieval_file)
        )
        row_ids = {row["id"] for row in rows}
        initial_cache = (
            seed_cache(load_arm_predictions(args.reuse_predictions, "B1", args.model))
            if args.reuse_predictions is not None
            else {}
        )
        b1_predictions = read_arm(args, rows, gold, "B1", row_ids, initial_cache)
        if args.phase == "b1":
            print(
                json.dumps(
                    {
                        "split": args.split,
                        "claims": len(row_ids),
                        "unknown": sum(
                            row["verdict"] == "UNKNOWN" for row in b1_predictions.values()
                        ),
                    },
                    indent=2,
                )
            )
            return
    else:
        rows = read_jsonl(args.retrieval_file)
        b1_predictions = load_arm_predictions(
            args.out_dir / "b1-predictions.jsonl", "B1", args.model
        )

    predictions = {"B1": b1_predictions}
    unknown_ids = {
        identifier
        for identifier, record in predictions["B1"].items()
        if record["verdict"] == "UNKNOWN"
    }
    retrieval_ids = {row["id"] for row in rows}
    missing = unknown_ids - retrieval_ids
    if missing:
        raise ValueError(f"retrieval is missing {len(missing)} B1 UNKNOWN claims")
    cache = seed_cache(b1_predictions)
    for arm in FALLBACK_ARMS:
        predictions[arm] = read_arm(args, rows, gold, arm, unknown_ids, cache)

    records = []
    for identifier in predictions["B1"]:
        b1 = predictions["B1"][identifier]
        arms = {"B1": {"verdict": b1["verdict"], "correct": b1["correct"]}}
        for fallback in FALLBACK_ARMS:
            verdict = hybrid_verdict(
                b1["verdict"],
                predictions[fallback].get(identifier, {"verdict": "UNKNOWN"})["verdict"],
            )
            arms[f"B1->{fallback}"] = {
                "verdict": verdict,
                "correct": is_correct(verdict, gold[identifier]),
            }
        records.append({"id": identifier, "gold": gold[identifier], "arms": arms})

    hybrid_arms = tuple(f"B1->{arm}" for arm in FALLBACK_ARMS)
    b1_correct = sum(row["arms"]["B1"]["correct"] for row in records)
    summary = {
        "split": args.split,
        "claims": len(records),
        "model": args.model,
        "fallback_claims": len(unknown_ids),
        "fallback_rate": len(unknown_ids) / len(records),
        "arms": {
            arm: {
                **arm_metrics(records, arm),
                "correct_over_b1": sum(row["arms"][arm]["correct"] for row in records) - b1_correct,
            }
            for arm in ("B1", *hybrid_arms)
        },
        "paired_vs_b1": {},
    }
    for arm in hybrid_arms:
        method_only = sum(
            row["arms"][arm]["correct"] and not row["arms"]["B1"]["correct"] for row in records
        )
        b1_only = sum(
            row["arms"]["B1"]["correct"] and not row["arms"][arm]["correct"] for row in records
        )
        summary["paired_vs_b1"][arm] = {
            "method_only_correct": method_only,
            "b1_only_correct": b1_only,
            "exact_two_sided_p": exact_paired_pvalue(method_only, b1_only),
        }
    h11 = summary["arms"]["B1->H10"]
    h9 = summary["arms"]["B1->H9"]
    b1 = summary["arms"]["B1"]
    paired = summary["paired_vs_b1"]["B1->H10"]
    summary["gates"] = {
        "accuracy_gain_at_least_3pp": h11["accuracy"] - b1["accuracy"] >= 0.03,
        "paired_p_below_0_05": paired["exact_two_sided_p"] < 0.05,
        "macro_f1_drop_at_most_0_01": h11["macro_f1"] >= b1["macro_f1"] - 0.01,
        "unknown_reduction_at_least_15pct": h11["unknown"] <= 0.85 * b1["unknown"],
        "ten_more_recoveries_than_h9": h11["correct_over_b1"] - h9["correct_over_b1"] >= 10,
        "fallback_rate_at_most_40pct": summary["fallback_rate"] <= 0.40,
    }
    summary["confirmed"] = all(summary["gates"].values())
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "b1", "fallback"), default="all")
    parser.add_argument("--retrieval-file", type=Path)
    parser.add_argument("--candidate-file", type=Path)
    parser.add_argument(
        "--reuse-predictions",
        type=Path,
        help="reuse reader verdicts only when id and evidence SHA-256 both match",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    args = parser.parse_args()
    if args.phase in ("all", "fallback") and args.retrieval_file is None:
        parser.error("--retrieval-file is required for all and fallback phases")
    if args.phase == "b1" and args.candidate_file is None:
        parser.error("--candidate-file is required for the b1 phase")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    read(args)


if __name__ == "__main__":
    main()
