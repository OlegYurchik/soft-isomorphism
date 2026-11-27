"""Extract only the query-guided HotpotQA paragraph frontier."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from factkg_e4_experiment import OnnxRelationEncoder
from hotpotqa_graph_pilot import (
    append_jsonl,
    auth_key,
    digest_paragraph,
    extract_task,
    read_jsonl,
    validate_query_graph,
)
from hotpotqa_structured_pilot import discovered_titles, normalized_label

from soft_isomorphism.hotpotqa import HotpotInput, bm25_sentences, load_hotpot_split


def grouped_paragraphs(example: HotpotInput) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for sentence in example.sentences:
        grouped.setdefault(sentence.title, []).append(sentence.text)
    return grouped


def bm25_title_order(example: HotpotInput) -> list[str]:
    result = []
    for sentence, _ in bm25_sentences(example, len(example.sentences)):
        if sentence.title not in result:
            result.append(sentence.title)
    return result


def seed_titles(example: HotpotInput, graph: dict, limit: int) -> list[str]:
    grouped = grouped_paragraphs(example)
    by_label = {normalized_label(title): title for title in grouped}
    labels = {normalized_label(node["label"]) for node in graph["nodes"] if node["label"] != "?"}
    exact = sorted(by_label[label] for label in labels & by_label.keys())
    return exact[:limit] if exact else bm25_title_order(example)[:1]


def run_batch(
    args: argparse.Namespace,
    key: str | None,
    tasks: list[tuple[str, str, str, list[str] | None]],
) -> list[tuple[str, dict]]:
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(extract_task, args, key, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            kind, row = future.result()
            results.append((kind, row))
            print(f"extracted {index}/{len(tasks)} {kind} valid={row['valid']}", flush=True)
    return results


def run(args: argparse.Namespace) -> None:
    inputs, _ = load_hotpot_split(
        args.parquet, args.split_file, args.split, args.limit, args.offset
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    query_path = args.out_dir / "query-extractions.jsonl"
    context_path = args.out_dir / "context-extractions.jsonl"
    queries = {row["id"]: row for row in read_jsonl(query_path)}
    contexts = {row["digest"]: row for row in read_jsonl(context_path)}
    for row in queries.values():
        if row["valid"]:
            try:
                validate_query_graph(row["graph"])
            except ValueError as exc:
                row["valid"] = False
                row["error"] = f"ValueError: {exc}"
    key = auth_key(args)
    new_rows: list[dict] = []

    query_tasks = []
    for example in inputs:
        cached = queries.get(example.id)
        if cached is None or (args.retry_invalid and not cached["valid"]):
            query_tasks.append(("query", example.id, example.question, None))
    for _, row in run_batch(args, key, query_tasks):
        queries[row["id"]] = row
        append_jsonl(query_path, row)
        new_rows.append(row)

    encoder = OnnxRelationEncoder()
    states = {}
    for example in inputs:
        query = queries[example.id]
        valid = bool(query["valid"])
        states[example.id] = {
            "example": example,
            "grouped": grouped_paragraphs(example),
            "bm25": bm25_title_order(example),
            "graph": query["graph"],
            "query_valid": valid,
            "selected": seed_titles(example, query["graph"], args.paragraph_limit) if valid else [],
            "frontier": 0,
            "graph_selected": 0,
            "filled": not valid,
        }

    while True:
        missing: dict[str, tuple[str, str, str, list[str]]] = {}
        for state in states.values():
            for title in state["selected"]:
                texts = state["grouped"][title]
                identifier = digest_paragraph(title, texts)
                if identifier not in contexts:
                    missing[identifier] = ("context", identifier, title, texts)
        for _, row in run_batch(args, key, list(missing.values())):
            contexts[row["digest"]] = row
            append_jsonl(context_path, row)
            new_rows.append(row)

        changed = False
        for state in states.values():
            if state["filled"]:
                continue
            selected = state["selected"]
            while state["frontier"] < len(selected) and len(selected) < args.paragraph_limit:
                title = selected[state["frontier"]]
                identifier = digest_paragraph(title, state["grouped"][title])
                if identifier not in contexts:
                    break
                state["frontier"] += 1
                for candidate in discovered_titles(
                    title,
                    state["grouped"],
                    contexts,
                    state["graph"],
                    encoder,
                    set(selected),
                ):
                    selected.append(candidate)
                    changed = True
                    if len(selected) == args.paragraph_limit:
                        break
            if state["frontier"] == len(selected) and len(selected) < args.paragraph_limit:
                state["graph_selected"] = len(selected)
                for title in state["bm25"]:
                    if title not in selected:
                        selected.append(title)
                    if len(selected) == args.paragraph_limit:
                        break
                state["filled"] = True
                changed = True
            elif len(selected) == args.paragraph_limit:
                state["graph_selected"] = len(selected)
                state["filled"] = True
        if not missing and not changed:
            break

    final_tasks: dict[str, tuple[str, str, str, list[str]]] = {}
    for state in states.values():
        for title in state["selected"]:
            texts = state["grouped"][title]
            identifier = digest_paragraph(title, texts)
            if identifier not in contexts:
                final_tasks[identifier] = ("context", identifier, title, texts)
    for _, row in run_batch(args, key, list(final_tasks.values())):
        contexts[row["digest"]] = row
        append_jsonl(context_path, row)
        new_rows.append(row)

    selections = [
        {
            "id": example.id,
            "query_valid": states[example.id]["query_valid"],
            "selected_titles": states[example.id]["selected"],
            "graph_selected": states[example.id]["graph_selected"],
        }
        for example in inputs
    ]
    (args.out_dir / f"graph-aware-selections-{len(inputs)}.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selections)
    )
    selected_digests = {
        digest_paragraph(title, states[row["id"]]["grouped"][title])
        for row in selections
        for title in row["selected_titles"]
    }
    summary = {
        "claims": len(inputs),
        "split": args.split,
        "offset": args.offset,
        "paragraph_limit": args.paragraph_limit,
        "query_graphs_valid": sum(row["query_valid"] for row in selections),
        "selected_contexts": sum(len(row["selected_titles"]) for row in selections),
        "unique_selected_contexts": len(selected_digests),
        "selected_contexts_valid": sum(contexts[digest]["valid"] for digest in selected_digests),
        "new_calls": len(new_rows),
        "new_tokens": sum(row.get("usage", {}).get("total_tokens", 0) for row in new_rows),
        "new_model_seconds": sum(row.get("seconds", 0.0) for row in new_rows),
    }
    (args.out_dir / f"graph-aware-extraction-summary-{len(inputs)}.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--split", choices=("development", "evaluation"), default="development")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--paragraph-limit", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--query-max-tokens", type=int, default=512)
    parser.add_argument("--context-max-tokens", type=int, default=1536)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--retry-invalid", action="store_true")
    args = parser.parse_args()
    if min(args.limit, args.paragraph_limit, args.workers) < 1:
        parser.error("limit, paragraph-limit, and workers must be positive")
    if args.offset < 0:
        parser.error("offset must be non-negative")
    run(args)


if __name__ == "__main__":
    main()
