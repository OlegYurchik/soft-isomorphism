"""Retry only invalid FactKG graph extractions with a larger output budget."""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from factkg_e1_pilot import (
    GRAPH_SCHEMA,
    PROMPTS,
    api_key_for,
    call_model,
    merge_views,
    parse_view,
    read_jsonl,
    write_jsonl,
)


def needs_retry(row: dict) -> bool:
    return row.get("valid_views", 0) == 0


def extraction_prompt(claim: str, instruction: str) -> tuple[str, str]:
    system = (
        "Return one JSON object only. Do not decide whether the claim is true. "
        "Use local node IDs. Copy named entity labels literally from the claim; "
        "never replace a name by a generic class like Person or Award. "
        "Use '?' only for an unspecified entity. "
        "Polarity must be positive or negative. "
        "Every quote must be an exact substring of the claim."
    )
    user = (
        instruction
        + "\nUse a concise relation phrase from the claim."
        + "\nClaim: "
        + claim
        + "\nSchema: {nodes:[{id,label}],"
        "edges:[{source,relation,target,polarity,quote}]}"
    )
    return system, user


def repaired_row(
    original: dict,
    raw: str,
    tokens: dict,
    seconds: float,
    max_tokens: int,
) -> dict:
    error = None
    try:
        view = parse_view(raw, original["text"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        view = []
        error = f"{type(exc).__name__}: {exc}"
    row = {
        **original,
        "graph": merge_views([view]),
        "valid_views": int(bool(view)),
        "raw_views": [raw],
        "usage": [{"tokens": tokens, "seconds": seconds}],
        "retry": {
            "source_valid_views": original.get("valid_views", 0),
            "source_finish_reason": (
                original.get("usage", [{}])[0].get("tokens", {}).get("finish_reason")
            ),
            "max_tokens": max_tokens,
            "error": error,
        },
    }
    return row


def run(args: argparse.Namespace) -> None:
    source_rows = read_jsonl(args.source)
    source_by_id = {row["id"]: row for row in source_rows}
    if len(source_by_id) != len(source_rows):
        raise ValueError("source contains duplicate ids")
    if any(row.get("extract_views") != 1 for row in source_rows):
        raise ValueError("retry currently requires one extraction view")
    if any(not row.get("open_relations", False) for row in source_rows):
        raise ValueError("retry currently requires open-relation extraction")

    existing = {row["id"]: row for row in read_jsonl(args.output)} if args.output.exists() else {}
    for identifier, row in existing.items():
        if identifier not in source_by_id:
            raise ValueError("output contains an id absent from source")
        retry = row.get("retry")
        if retry and retry.get("max_tokens") != args.max_tokens:
            raise ValueError("cached retry has a different max_tokens setting")

    key = api_key_for(args)
    pending = [row for row in source_rows if needs_retry(row) and row["id"] not in existing]

    def retry_one(row: dict) -> dict:
        system, user = extraction_prompt(row["text"], PROMPTS[0])
        for attempt in range(3):
            try:
                raw, tokens, seconds = call_model(
                    args.server_url,
                    system,
                    user,
                    args.max_tokens,
                    schema=GRAPH_SCHEMA,
                    model=args.model,
                    api_key=key,
                    json_mode=args.json_mode,
                )
                return repaired_row(row, raw, tokens, seconds, args.max_tokens)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                if attempt == 2 or exc.code < 500:
                    raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
                time.sleep(2**attempt)
            except (TimeoutError, urllib.error.URLError, ssl.SSLError):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def save(row: dict) -> None:
        existing[row["id"]] = row
        combined = [
            existing.get(source["id"], source)
            for source in source_rows
            if source["id"] in existing or not needs_retry(source)
        ]
        write_jsonl(args.output, combined)
        print(
            f"retried {len(existing)}/{len(pending)} {row['id'][:12]} "
            f"edges={len(row['graph']['edges'])}",
            flush=True,
        )

    if args.workers == 1:
        for row in map(retry_one, pending):
            save(row)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(retry_one, row) for row in pending]
            for future in as_completed(futures):
                save(future.result())

    final = [existing.get(row["id"], row) for row in source_rows]
    if len(final) != len(source_rows):
        raise AssertionError("retry output lost source rows")
    write_jsonl(args.output, final)

    retried = [row for row in final if "retry" in row]
    unchanged = [
        row == source_by_id[row["id"]] for row in final if not needs_retry(source_by_id[row["id"]])
    ]
    summary = {
        "claims": len(final),
        "retried": len(retried),
        "recovered": sum(row["valid_views"] > 0 for row in retried),
        "still_invalid": sum(row["valid_views"] == 0 for row in retried),
        "unchanged_valid_rows": sum(unchanged),
        "expected_unchanged_valid_rows": len(unchanged),
        "calls": len(retried),
        "total_tokens": sum(
            usage.get("tokens", {}).get("total_tokens", 0)
            for row in retried
            for usage in row.get("usage", [])
        ),
        "model_seconds": sum(
            usage.get("seconds", 0) for row in retried for usage in row.get("usage", [])
        ),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--json-mode", choices=("schema", "object"), default="schema")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.max_tokens <= 256:
        parser.error("max-tokens must be greater than the original 256-token budget")
    if args.workers < 1:
        parser.error("workers must be positive")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
