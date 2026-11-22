"""Run the frozen HotpotQA sentence-BM25 feasibility baseline."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from factkg_e1_pilot import call_model

from soft_isomorphism.hotpotqa import (
    answer_metrics,
    bm25_sentences,
    load_hotpot_split,
    supporting_metrics,
)


def api_key(args: argparse.Namespace) -> str | None:
    if args.kilo_auth_provider:
        auth_path = Path.home() / ".local/share/kilo/auth.json"
        return json.loads(auth_path.read_text())[args.kilo_auth_provider]["key"]
    return os.getenv(args.api_key_env)


def parse_answer(raw: str) -> str:
    try:
        value = json.loads(raw).get("answer")
    except (AttributeError, json.JSONDecodeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


def mean(records: list[dict], key: str) -> float:
    return sum(record[key] for record in records) / len(records) if records else 0.0


def run(args: argparse.Namespace) -> None:
    inputs, gold = load_hotpot_split(args.parquet, args.split_file, args.split, args.limit)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    retrieval_path = args.out_dir / "bm25-retrieval.jsonl"
    retrieval_rows = []
    metric_rows = []
    started = time.monotonic()
    for example in inputs:
        ranked = bm25_sentences(example, args.evidence_budget)
        evidence = [
            {
                "title": sentence.title,
                "sent_id": sentence.sent_id,
                "text": sentence.text,
                "score": score,
            }
            for sentence, score in ranked
        ]
        retrieval_rows.append(
            {"id": example.id, "question": example.question, "evidence": evidence}
        )
        predicted = {(row["title"], row["sent_id"]) for row in evidence}
        metric_rows.append(supporting_metrics(predicted, gold[example.id].supporting_facts))
    retrieval_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in retrieval_rows)
    )
    retrieval_seconds = time.monotonic() - started

    predictions_path = args.out_dir / "bm25-predictions.jsonl"
    existing = (
        {
            row["id"]: row
            for row in (json.loads(line) for line in predictions_path.read_text().splitlines())
        }
        if predictions_path.exists()
        else {}
    )
    key = api_key(args)
    answer_rows = []
    for row in retrieval_rows:
        identifier = row["id"]
        if identifier not in existing:
            evidence = [
                {"title": item["title"], "sent_id": item["sent_id"], "text": item["text"]}
                for item in row["evidence"]
            ]
            raw, usage, seconds = call_model(
                args.server_url,
                "Answer the question using only the supplied evidence sentences. "
                "Return one JSON object with one short answer string. Do not explain.",
                "Question: "
                + row["question"]
                + "\nEvidence: "
                + json.dumps(evidence, ensure_ascii=False)
                + '\nReturn {"answer":"..."}.',
                args.reader_max_tokens,
                model=args.model,
                api_key=key,
                json_mode="object",
            )
            answer = parse_answer(raw)
            record = {
                "id": identifier,
                "arm": "B1-Hotpot",
                "model": args.model,
                "answer": answer,
                "valid": bool(answer),
                "usage": usage,
                "reader_seconds": seconds,
            }
            with predictions_path.open("a") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing[identifier] = record
            print(f"read B1-Hotpot {len(existing)}/{len(inputs)} {identifier}", flush=True)
        answer_rows.append(answer_metrics(existing[identifier]["answer"], gold[identifier].answer))

    summary = {
        "split": args.split,
        "claims": len(inputs),
        "evidence_budget": args.evidence_budget,
        "retrieval_seconds": retrieval_seconds,
        "answer_em": mean(answer_rows, "answer_em"),
        "answer_f1": mean(answer_rows, "answer_f1"),
        "support_em": mean(metric_rows, "support_em"),
        "support_precision": mean(metric_rows, "support_precision"),
        "support_recall": mean(metric_rows, "support_recall"),
        "support_f1": mean(metric_rows, "support_f1"),
        "invalid_answers": sum(not existing[example.id]["valid"] for example in inputs),
        "reader_calls": sum(bool(existing[example.id].get("usage")) for example in inputs),
        "reader_tokens": sum(
            existing[example.id].get("usage", {}).get("total_tokens", 0) for example in inputs
        ),
        "reader_seconds": sum(existing[example.id].get("reader_seconds", 0) for example in inputs),
    }
    (args.out_dir / "bm25-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--split", choices=("development", "evaluation"), default="development")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--evidence-budget", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=128)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit must be positive")
    if args.evidence_budget < 1:
        parser.error("evidence-budget must be positive")
    run(args)


if __name__ == "__main__":
    main()
