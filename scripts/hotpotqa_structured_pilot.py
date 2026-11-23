"""Run the preregistered graph-retrieval arm of the HotpotQA feasibility pilot."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from factkg_e1_pilot import call_model
from factkg_e4_experiment import OnnxRelationEncoder
from factkg_h7_soft_matching import directed_arcs, edge_text, query_edge_text
from factkg_h10_endpoint_paths import match_row
from hotpotqa_bm25_pilot import api_key, mean, parse_answer
from hotpotqa_graph_pilot import digest_paragraph, read_jsonl

from soft_isomorphism.hotpotqa import (
    HotpotInput,
    Sentence,
    answer_metrics,
    bm25_sentences,
    load_hotpot_split,
    supporting_metrics,
)
from soft_isomorphism.matching import label_distance


def candidate_domains(
    graph: dict, triples: list[dict], limit: int = 5, *, freeze_exact: bool = False
) -> dict[str, list[str]]:
    entities = sorted({triple[key] for triple in triples for key in ("source", "target")})
    domains = {}
    for node in graph["nodes"]:
        label = node["label"]
        ranked = sorted(entities, key=lambda value: (label_distance(label, value), value))
        exact = [value for value in ranked if label_distance(label, value) == 0.0]
        domains[node["id"]] = (
            [] if label == "?" else (exact if freeze_exact and exact else ranked[:limit])
        )
    return domains


def evidence_from_match(
    example: HotpotInput, graph_evidence: list[dict], budget: int
) -> tuple[list[dict], int]:
    available = {(sentence.title, sentence.sent_id): sentence for sentence in example.sentences}
    selected: list[Sentence] = []
    seen = set()
    for triple in graph_evidence:
        key = (triple.get("title"), triple.get("sent_id"))
        if key in available and key not in seen:
            selected.append(available[key])
            seen.add(key)
        if len(selected) == budget:
            break
    graph_count = len(selected)
    for sentence, _ in bm25_sentences(example, len(example.sentences)):
        key = (sentence.title, sentence.sent_id)
        if key not in seen:
            selected.append(sentence)
            seen.add(key)
        if len(selected) == budget:
            break
    return (
        [
            {"title": sentence.title, "sent_id": sentence.sent_id, "text": sentence.text}
            for sentence in selected
        ],
        graph_count,
    )


def shortlisted_titles(
    example: HotpotInput,
    limit: int | None,
    graph: dict | None = None,
    *,
    anchor_first: bool = False,
) -> set[str]:
    titles: list[str] = []
    if anchor_first and graph is not None:
        query_labels = {
            " ".join(node["label"].casefold().split())
            for node in graph["nodes"]
            if node["label"] != "?"
        }
        titles.extend(
            sorted(
                {
                    sentence.title
                    for sentence in example.sentences
                    if " ".join(sentence.title.casefold().split()) in query_labels
                }
            )
        )
    for sentence, _ in bm25_sentences(example, len(example.sentences)):
        if sentence.title not in titles:
            titles.append(sentence.title)
    return set(titles if limit is None else titles[:limit])


def normalized_label(value: str) -> str:
    return " ".join(value.casefold().split())


def discovered_titles(
    title: str,
    grouped: dict[str, list[str]],
    contexts: dict[str, dict],
    graph: dict,
    encoder: OnnxRelationEncoder,
    excluded: set[str],
) -> list[str]:
    row = contexts.get(digest_paragraph(title, grouped[title]))
    if row is None or not row["valid"]:
        return []
    title_by_label = {normalized_label(value): value for value in grouped}
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    query_texts = [query_edge_text(edge, labels) for edge in graph["edges"]]
    candidates: dict[str, float] = {}
    for triple in row["triples"]:
        arcs = directed_arcs([triple])
        score = max(
            (
                encoder.similarity(
                    query_text,
                    edge_text(arc["source"], arc["relation"], arc["target"]),
                )
                for query_text in query_texts
                for arc in arcs
            ),
            default=0.0,
        )
        for endpoint in (triple["source"], triple["target"]):
            candidate = title_by_label.get(normalized_label(endpoint))
            if candidate is not None and candidate not in excluded:
                candidates[candidate] = max(candidates.get(candidate, 0.0), score)
    return sorted(candidates, key=lambda value: (-candidates[value], value))


def graph_aware_titles(
    example: HotpotInput,
    contexts: dict[str, dict],
    graph: dict | None,
    limit: int,
    encoder: OnnxRelationEncoder,
) -> list[str]:
    if graph is None:
        return []
    grouped: dict[str, list[str]] = {}
    for sentence in example.sentences:
        grouped.setdefault(sentence.title, []).append(sentence.text)
    title_by_label = {normalized_label(title): title for title in grouped}
    bm25_order = []
    for sentence, _ in bm25_sentences(example, len(example.sentences)):
        if sentence.title not in bm25_order:
            bm25_order.append(sentence.title)

    selected = []
    query_labels = {
        normalized_label(node["label"]) for node in graph["nodes"] if node["label"] != "?"
    }
    selected.extend(sorted(title_by_label[label] for label in query_labels & title_by_label.keys()))
    if not selected and bm25_order:
        selected.append(bm25_order[0])
    selected = selected[:limit]

    frontier = 0
    while len(selected) < limit and frontier < len(selected):
        title = selected[frontier]
        frontier += 1
        for candidate in discovered_titles(title, grouped, contexts, graph, encoder, set(selected)):
            selected.append(candidate)
            if len(selected) == limit:
                break

    for title in bm25_order:
        if len(selected) == limit:
            break
        if title not in selected:
            selected.append(title)
    return selected


def paragraph_triples(
    example: HotpotInput,
    contexts: dict[str, dict],
    paragraph_limit: int | None,
    graph: dict | None = None,
    *,
    anchor_first: bool = False,
    graph_aware: bool = False,
    encoder: OnnxRelationEncoder | None = None,
) -> tuple[list[dict], int, list[str]]:
    grouped: dict[str, list[str]] = {}
    for sentence in example.sentences:
        grouped.setdefault(sentence.title, []).append(sentence.text)
    triples = []
    invalid = 0
    if graph_aware:
        if paragraph_limit is None or encoder is None:
            raise ValueError("graph-aware retrieval requires paragraph limit and encoder")
        selected = graph_aware_titles(example, contexts, graph, paragraph_limit, encoder)
    else:
        selected = sorted(
            shortlisted_titles(example, paragraph_limit, graph, anchor_first=anchor_first)
        )
    for title, texts in grouped.items():
        if title not in selected:
            continue
        row = contexts.get(digest_paragraph(title, texts))
        if row is None or not row["valid"]:
            invalid += 1
        else:
            triples.extend(row["triples"])
    return triples, invalid, selected


def run(args: argparse.Namespace) -> None:
    inputs, gold = load_hotpot_split(
        args.parquet, args.split_file, "development", args.limit, args.offset
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    queries = {row["id"]: row for row in read_jsonl(args.graph_dir / "query-extractions.jsonl")}
    contexts = {
        row["digest"]: row for row in read_jsonl(args.graph_dir / "context-extractions.jsonl")
    }
    encoder = OnnxRelationEncoder()
    retrieval_rows = []
    support_rows = []
    started = time.monotonic()
    for index, example in enumerate(inputs, start=1):
        query = queries.get(example.id)
        triples, invalid_contexts, selected_titles = paragraph_triples(
            example,
            contexts,
            args.paragraph_limit,
            query["graph"] if query is not None and query["valid"] else None,
            anchor_first=args.anchor_first,
            graph_aware=args.graph_aware,
            encoder=encoder,
        )
        result = None
        if query is not None and query["valid"] and triples:
            row = {
                "graph": query["graph"],
                "pool_triples": triples,
                "candidate_ids": candidate_domains(
                    query["graph"], triples, freeze_exact=args.freeze_exact
                ),
            }
            result = match_row(
                row,
                encoder,
                candidates_per_node=1,
                expanded_node_penalty=0.0,
                contextual_proposals=args.contextual_proposals,
            )
        graph_evidence = result["match"]["evidence"] if result else []
        evidence, graph_count = evidence_from_match(example, graph_evidence, args.evidence_budget)
        mode = "graph" if graph_count else "fallback"
        record = {
            "id": example.id,
            "question": example.question,
            "mode": mode,
            "triples": len(triples),
            "invalid_contexts": invalid_contexts,
            "selected_contexts": len(selected_titles),
            "selected_titles": selected_titles,
            "graph_sentences": graph_count,
            "match_cost": result["match"]["cost"] if result else None,
            "evidence": evidence,
        }
        retrieval_rows.append(record)
        predicted = {(item["title"], item["sent_id"]) for item in evidence}
        support_rows.append(supporting_metrics(predicted, gold[example.id].supporting_facts))
        print(f"matched {index}/{len(inputs)} {example.id} mode={mode}", flush=True)
    retrieval_seconds = time.monotonic() - started
    (args.out_dir / "structured-retrieval.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in retrieval_rows)
    )

    retrieval_summary = {
        "split": "development",
        "claims": len(inputs),
        "offset": args.offset,
        "evidence_budget": args.evidence_budget,
        "paragraph_limit": args.paragraph_limit,
        "anchor_first": args.anchor_first,
        "freeze_exact": args.freeze_exact,
        "contextual_proposals": args.contextual_proposals,
        "graph_aware": args.graph_aware,
        "hypothetical_extraction_calls": len(inputs)
        + sum(row["selected_contexts"] for row in retrieval_rows),
        "retrieval_seconds": retrieval_seconds,
        "graph_mode": sum(row["mode"] == "graph" for row in retrieval_rows),
        "fallback_mode": sum(row["mode"] == "fallback" for row in retrieval_rows),
        "support_em": mean(support_rows, "support_em"),
        "support_precision": mean(support_rows, "support_precision"),
        "support_recall": mean(support_rows, "support_recall"),
        "support_f1": mean(support_rows, "support_f1"),
    }
    (args.out_dir / "structured-retrieval-summary.json").write_text(
        json.dumps(retrieval_summary, indent=2) + "\n"
    )
    if args.retrieval_only:
        print(json.dumps(retrieval_summary, indent=2))
        return

    predictions_path = args.out_dir / "structured-predictions.jsonl"
    existing = (
        {row["id"]: row for row in read_jsonl(predictions_path)}
        if predictions_path.exists()
        else {}
    )
    key = api_key(args)
    answer_rows = []
    for index, row in enumerate(retrieval_rows, start=1):
        identifier = row["id"]
        if identifier not in existing:
            raw, usage, seconds = call_model(
                args.server_url,
                "Answer the question using only the supplied evidence sentences. "
                "Return one JSON object with one short answer string. Do not explain.",
                "Question: "
                + row["question"]
                + "\nEvidence: "
                + json.dumps(row["evidence"], ensure_ascii=False)
                + '\nReturn {"answer":"..."}.',
                args.reader_max_tokens,
                model=args.model,
                api_key=key,
                json_mode="object",
            )
            answer = parse_answer(raw)
            record = {
                "id": identifier,
                "arm": "H10-transfer-Hotpot",
                "model": args.model,
                "answer": answer,
                "valid": bool(answer),
                "usage": usage,
                "reader_seconds": seconds,
            }
            with predictions_path.open("a") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            existing[identifier] = record
            print(f"read structured {index}/{len(inputs)} {identifier}", flush=True)
        answer_rows.append(answer_metrics(existing[identifier]["answer"], gold[identifier].answer))

    summary = {
        **retrieval_summary,
        "answer_em": mean(answer_rows, "answer_em"),
        "answer_f1": mean(answer_rows, "answer_f1"),
        "support_em": mean(support_rows, "support_em"),
        "support_precision": mean(support_rows, "support_precision"),
        "support_recall": mean(support_rows, "support_recall"),
        "support_f1": mean(support_rows, "support_f1"),
        "invalid_answers": sum(not existing[example.id]["valid"] for example in inputs),
        "reader_calls": sum(bool(existing[example.id].get("usage")) for example in inputs),
        "reader_tokens": sum(
            existing[example.id].get("usage", {}).get("total_tokens", 0) for example in inputs
        ),
        "reader_seconds": sum(existing[example.id].get("reader_seconds", 0) for example in inputs),
    }
    (args.out_dir / "structured-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--evidence-budget", type=int, default=5)
    parser.add_argument("--paragraph-limit", type=int)
    parser.add_argument("--anchor-first", action="store_true")
    parser.add_argument("--freeze-exact", action="store_true")
    parser.add_argument("--contextual-proposals", action="store_true")
    parser.add_argument("--graph-aware", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=128)
    args = parser.parse_args()
    if (
        args.limit < 1
        or args.offset < 0
        or args.evidence_budget < 1
        or (args.paragraph_limit is not None and args.paragraph_limit < 1)
    ):
        parser.error("limits must be positive and offset must be non-negative")
    if args.graph_aware and args.paragraph_limit is None:
        parser.error("graph-aware retrieval requires paragraph-limit")
    run(args)


if __name__ == "__main__":
    main()
