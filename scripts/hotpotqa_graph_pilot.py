"""Extract grounded query and context graphs for the HotpotQA feasibility pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from factkg_e1_pilot import call_model, merge_views, parse_view

from soft_isomorphism.hotpotqa import Sentence, load_hotpot_split


def digest_paragraph(title: str, sentences: list[str]) -> str:
    payload = json.dumps([title, sentences], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def parse_context_graph(raw: str, title: str, sentences: list[str]) -> list[dict]:
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("nodes"), list)
        or not isinstance(data.get("edges"), list)
    ):
        raise ValueError("expected nodes and edges lists")
    labels = {}
    corpus = " ".join(sentences).casefold()
    for node in data["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), (str, int)):
            raise ValueError("invalid node id")
        label = node.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("invalid node label")
        if label.casefold() != title.casefold() and label.casefold() not in corpus:
            raise ValueError("node label is not grounded in title or paragraph")
        labels[str(node["id"])] = " ".join(label.casefold().split())

    def resolve_endpoint(value: object) -> str:
        identifier = str(value)
        if identifier in labels:
            return identifier
        normalized = " ".join(identifier.casefold().split())
        matches = [node_id for node_id, label in labels.items() if label == normalized]
        if len(matches) == 1:
            return matches[0]
        raise ValueError("invalid edge endpoints")

    triples = []
    for edge in data["edges"]:
        if not isinstance(edge, dict):
            raise ValueError("invalid edge")
        source, target = resolve_endpoint(edge.get("source")), resolve_endpoint(edge.get("target"))
        relation = edge.get("relation")
        polarity = edge.get("polarity")
        sent_id = edge.get("sent_id")
        quote = edge.get("quote")
        if not isinstance(relation, str) or not relation.strip():
            raise ValueError("missing relation")
        if polarity not in ("positive", "negative"):
            raise ValueError("invalid polarity")
        if not isinstance(sent_id, int) or not 0 <= sent_id < len(sentences):
            raise ValueError("invalid sentence id")
        if not isinstance(quote, str) or quote not in sentences[sent_id]:
            raise ValueError("quote is not an exact sentence substring")
        triples.append(
            {
                "source": labels[source],
                "relation": " ".join(relation.casefold().split()),
                "target": labels[target],
                "polarity": polarity,
                "title": title,
                "sent_id": sent_id,
                "quote": quote,
            }
        )
    return triples


def query_prompt(question: str) -> tuple[str, str]:
    system = (
        "Return one JSON object only. Extract the relation structure of the question. "
        "Use local node IDs and literal entity labels from the question. "
        "Represent the requested unknown answer as a node with label '?'. "
        "Every quote must be an exact substring of the question."
    )
    user = (
        "Question: "
        + question
        + "\nReturn {nodes:[{id,label}],edges:[{source,relation,target,polarity,quote}]}. "
        "Polarity is positive or negative."
    )
    return system, user


def validate_query_graph(graph: dict) -> None:
    unknowns = [node["id"] for node in graph["nodes"] if node["label"] == "?"]
    if len(unknowns) != 1:
        raise ValueError("query graph must contain exactly one '?' node")
    unknown = unknowns[0]
    if not any(unknown in (edge["source"], edge["target"]) for edge in graph["edges"]):
        raise ValueError("unknown node must be incident to a query edge")


def context_prompt(title: str, sentences: list[str]) -> tuple[str, str]:
    numbered = "\n".join(f"[{index}] {sentence}" for index, sentence in enumerate(sentences))
    system = (
        "Return one JSON object only. Extract explicitly stated subject-relation-object facts. "
        "The article title may be used as a subject even when a sentence uses a pronoun. "
        "Entity labels must be literal substrings of the title or paragraph. "
        "Every edge must include the source sentence id and an exact quote from that sentence. "
        "Return at most 8 central edges and at most 12 nodes. "
        "Use local node IDs in edge endpoints. "
        "Keep JSON compact."
    )
    user = (
        f"Title: {title}\nSentences:\n{numbered}\n"
        "Return {nodes:[{id,label}],edges:[{source,relation,target,polarity,sent_id,quote}]}. "
        "Polarity is positive or negative."
    )
    return system, user


def auth_key(args: argparse.Namespace) -> str | None:
    if args.kilo_auth_provider:
        path = Path.home() / ".local/share/kilo/auth.json"
        return json.loads(path.read_text())[args.kilo_auth_provider]["key"]
    return os.getenv(args.api_key_env)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_task(
    args: argparse.Namespace,
    key: str | None,
    task: tuple[str, str, str, list[str] | None],
) -> tuple[str, dict]:
    kind, identifier, text, sentences = task
    system, user = query_prompt(text) if kind == "query" else context_prompt(text, sentences or [])
    for attempt in range(3):
        try:
            raw, usage, seconds = call_model(
                args.server_url,
                system,
                user,
                args.query_max_tokens if kind == "query" else args.context_max_tokens,
                model=args.model,
                api_key=key,
                json_mode="object",
            )
            break
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    error = None
    if kind == "query":
        try:
            graph = merge_views([parse_view(raw, text)])
            validate_query_graph(graph)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            graph = {"nodes": [], "edges": []}
            error = f"{type(exc).__name__}: {exc}"
        row = {
            "id": identifier,
            "question": text,
            "graph": graph,
            "valid": bool(graph["edges"]),
            "raw": raw,
            "usage": usage,
            "seconds": seconds,
            "error": error,
        }
    else:
        try:
            triples = parse_context_graph(raw, text, sentences or [])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            triples = []
            error = f"{type(exc).__name__}: {exc}"
        row = {
            "digest": identifier,
            "title": text,
            "sentences": sentences,
            "triples": triples,
            "valid": bool(triples),
            "raw": raw,
            "usage": usage,
            "seconds": seconds,
            "error": error,
        }
    return kind, row


def run(args: argparse.Namespace) -> None:
    inputs, _ = load_hotpot_split(args.parquet, args.split_file, "development", args.limit)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    query_path = args.out_dir / "query-extractions.jsonl"
    context_path = args.out_dir / "context-extractions.jsonl"
    queries = {row["id"]: row for row in read_jsonl(query_path)}
    contexts = {row["digest"]: row for row in read_jsonl(context_path)}
    for row in queries.values():
        if not row["valid"]:
            continue
        try:
            validate_query_graph(row["graph"])
        except ValueError as exc:
            row["valid"] = False
            row["error"] = f"ValueError: {exc}"
    key = auth_key(args)

    tasks = []
    for example in inputs:
        if example.id not in queries or (args.retry_invalid and not queries[example.id]["valid"]):
            tasks.append(("query", example.id, example.question, None))
        grouped: dict[str, list[Sentence]] = {}
        for sentence in example.sentences:
            grouped.setdefault(sentence.title, []).append(sentence)
        for title, paragraph in grouped.items():
            texts = [sentence.text for sentence in paragraph]
            identifier = digest_paragraph(title, texts)
            if identifier not in contexts or (
                args.retry_invalid and not contexts[identifier]["valid"]
            ):
                tasks.append(("context", identifier, title, texts))

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(extract_task, args, key, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            kind, row = future.result()
            if kind == "query":
                queries[row["id"]] = row
                append_jsonl(query_path, row)
            else:
                contexts[row["digest"]] = row
                append_jsonl(context_path, row)
            print(f"extracted {index}/{len(tasks)} {kind} valid={row['valid']}", flush=True)

    selected_contexts = set()
    for example in inputs:
        grouped: dict[str, list[str]] = {}
        for sentence in example.sentences:
            grouped.setdefault(sentence.title, []).append(sentence.text)
        selected_contexts.update(digest_paragraph(title, texts) for title, texts in grouped.items())
    query_rows = [queries[example.id] for example in inputs]
    context_rows = [contexts[identifier] for identifier in selected_contexts]
    summary = {
        "claims": len(inputs),
        "query_graphs_valid": sum(row["valid"] for row in query_rows),
        "context_paragraphs": len(context_rows),
        "context_graphs_valid": sum(row["valid"] for row in context_rows),
        "calls": sum(bool(row.get("usage")) for row in [*query_rows, *context_rows]),
        "tokens": sum(
            row.get("usage", {}).get("total_tokens", 0) for row in [*query_rows, *context_rows]
        ),
        "model_seconds": sum(row.get("seconds", 0) for row in [*query_rows, *context_rows]),
    }
    (args.out_dir / "extraction-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--query-max-tokens", type=int, default=512)
    parser.add_argument("--context-max-tokens", type=int, default=1536)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--retry-invalid",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    if args.limit < 1 or args.workers < 1:
        parser.error("limit and workers must be positive")
    run(args)


if __name__ == "__main__":
    main()
