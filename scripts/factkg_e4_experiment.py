"""Frozen E4/B4 reranking experiment over FactKG query graphs.

The prepare stage loads the large KG once and writes a label-free candidate file.
The score stage runs the pinned ONNX relation encoder without loading the KG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from factkg_e1_pilot import (
    api_key_for,
    bm25_incident,
    call_model,
    candidate_pool,
    digest,
    read_jsonl,
    write_jsonl,
)

from soft_isomorphism.matching import Edge, Node, Triple, label_distance
from soft_isomorphism.search import beam_search

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
SIMILARITY_THRESHOLD = 0.55
PATH_WEIGHT = 0.2


def relation_text(value: str) -> str:
    """Use the same readable predicate for query and DBpedia relations."""
    value = value.removeprefix("~").replace("_", " ")
    return " ".join(re.sub(r"([a-z])([A-Z])", r"\1 \2", value).casefold().split())


class OnnxRelationEncoder:
    """Sentence Transformers mean pooling over a pinned MiniLM ONNX checkpoint."""

    def __init__(self) -> None:
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.np = np
        model = hf_hub_download(MODEL_ID, "onnx/model.onnx", revision=MODEL_REVISION)
        tokenizer = hf_hub_download(MODEL_ID, "tokenizer.json", revision=MODEL_REVISION)
        self.model_sha256 = hashlib.sha256(Path(model).read_bytes()).hexdigest()
        self.tokenizer_sha256 = hashlib.sha256(Path(tokenizer).read_bytes()).hexdigest()
        self.session = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(tokenizer)
        self.tokenizer.enable_padding()
        self.tokenizer.enable_truncation(max_length=128)
        self.cache: dict[str, object] = {}

    def encode_many(self, relations: set[str]) -> None:
        pending = sorted({relation_text(r) for r in relations} - self.cache.keys())
        for start in range(0, len(pending), 64):
            batch = pending[start : start + 64]
            encoded = self.tokenizer.encode_batch(batch)
            ids = self.np.asarray([row.ids for row in encoded], dtype="int64")
            masks = self.np.asarray([row.attention_mask for row in encoded], dtype="int64")
            types = self.np.asarray([row.type_ids for row in encoded], dtype="int64")
            hidden = self.session.run(
                None, {"input_ids": ids, "attention_mask": masks, "token_type_ids": types}
            )[0]
            pooled = (hidden * masks[..., None]).sum(axis=1) / masks.sum(axis=1)[:, None]
            pooled /= self.np.maximum(self.np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            self.cache.update(zip(batch, pooled, strict=True))

    def similarity(self, left: str, right: str) -> float:
        a, b = relation_text(left), relation_text(right)
        if a not in self.cache or b not in self.cache:
            self.encode_many({a, b})
        return max(0.0, min(1.0, float(self.np.dot(self.cache[a], self.cache[b]))))


def query_paths(graph: dict) -> list[tuple[int, ...]]:
    """Enumerate directed simple query paths of two or three edges."""
    edges = graph["edges"]
    outgoing: dict[str, list[int]] = defaultdict(list)
    for index, edge in enumerate(edges):
        outgoing[edge["source"]].append(index)
    found: set[tuple[int, ...]] = set()

    def visit(node: str, used_nodes: set[str], path: tuple[int, ...]) -> None:
        if len(path) in (2, 3):
            found.add(path)
        if len(path) == 3:
            return
        for index in outgoing[node]:
            next_node = edges[index]["target"]
            if next_node not in used_nodes:
                visit(next_node, used_nodes | {next_node}, (*path, index))

    for node in graph["nodes"]:
        visit(node["id"], {node["id"]}, ())
    return sorted(found)


def mapping_evidence(
    graph: dict,
    mapping: dict[str, str | None],
    triples: list[Triple],
    similarity: Callable[[str, str], float],
) -> dict:
    """Score one mapping and select only real directed KG triples."""
    by_pair: dict[tuple[str, str], list[Triple]] = defaultdict(list)
    for triple in triples:
        by_pair[triple.source, triple.target].append(triple)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    node_cost = sum(
        0.8
        if mapping[node_id] is None
        else (0.0 if label == "?" else label_distance(label, mapping[node_id].replace("_", " ")))
        for node_id, label in labels.items()
    ) / len(labels)
    witnesses: list[tuple[Triple, float] | None] = []
    distances = []
    for edge in graph["edges"]:
        source, target = mapping[edge["source"]], mapping[edge["target"]]
        choices = by_pair.get((source, target), []) if source and target else []
        ranked = sorted(
            ((similarity(edge["relation"], triple.relation), triple) for triple in choices),
            key=lambda item: (-item[0], item[1].relation, item[1].source, item[1].target),
        )
        witnesses.append((ranked[0][1], ranked[0][0]) if ranked else None)
        distances.append(1.0 - ranked[0][0] if ranked else 1.0)
    paths = query_paths(graph)
    complete = [
        path
        for path in paths
        if all(witnesses[index] and witnesses[index][1] >= SIMILARITY_THRESHOLD for index in path)
    ]
    path_penalty = 1.0 - len(complete) / len(paths) if paths else 0.0
    b4_cost = 0.3 * node_cost + 0.7 * sum(distances) / len(distances)
    priority = {index for path in complete for index in path}
    ordered = sorted(range(len(witnesses)), key=lambda index: (index not in priority, index))
    evidence = []
    for index in ordered:
        witness = witnesses[index]
        if witness is None or witness[1] < SIMILARITY_THRESHOLD:
            continue
        triple = witness[0]
        item = {"source": triple.source, "relation": triple.relation, "target": triple.target}
        if item not in evidence:
            evidence.append(item)
    return {
        "b4_cost": b4_cost,
        "e4_cost": b4_cost + PATH_WEIGHT * path_penalty,
        "query_paths": len(paths),
        "complete_paths": len(complete),
        "evidence": evidence[:20],
    }


def rerank_row(row: dict, similarity: Callable[[str, str], float]) -> dict:
    result = {
        "id": row["id"],
        "text": row["text"],
        "graph": row["graph"],
        "arms": {},
        "b1_evidence": row.get("b1_evidence", []),
        "top_mappings": len(row.get("mappings", [])),
    }
    if row["status"] != "ok":
        for arm in ("B4", "E4"):
            result["arms"][arm] = {"status": row["status"], "evidence": []}
        return result
    triples = [Triple(**item) for item in row["pool_triples"]]
    scored = [
        (mapping, mapping_evidence(row["graph"], mapping, triples, similarity))
        for mapping in row["mappings"]
    ]
    for arm, key in (("B4", "b4_cost"), ("E4", "e4_cost")):
        mapping, detail = min(
            scored,
            key=lambda item: (
                item[1][key],
                tuple("~" if value is None else value for _, value in sorted(item[0].items())),
            ),
        )
        result["arms"][arm] = {"status": "ok", "mapping": mapping, **detail}
    result["top50_complete_path_min"] = min(detail["complete_paths"] for _, detail in scored)
    result["top50_complete_path_max"] = max(detail["complete_paths"] for _, detail in scored)
    return result


def prepare(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.extract_file)
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    index = sqlite3.connect(args.name_index)
    output = args.out_dir / "candidate-pools.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    for row in rows:
        if row["id"] in existing:
            if (
                existing[row["id"]]["graph"] != row["graph"]
                or existing[row["id"]]["text"] != row["text"]
            ):
                raise ValueError(f"cached candidate pool has a different extraction: {row['id']}")
            continue
        graph = row["graph"]
        result = {"id": row["id"], "text": row["text"], "graph": graph}
        if not graph["nodes"] or not graph["edges"]:
            result.update(
                {"status": "empty_graph", "mappings": [], "pool_triples": [], "b1_evidence": []}
            )
        else:
            nodes, triples, candidates = candidate_pool(kg, graph, row["text"], index)
            qnodes = [Node(item["id"], item["label"]) for item in graph["nodes"]]
            qedges = [
                Edge(item["source"], item["relation"], item["target"]) for item in graph["edges"]
            ]
            outcome = beam_search(qnodes, qedges, nodes, triples, candidates, top_k=50)
            anchors = {identifier for ids in candidates.values() for identifier in ids}
            b1 = bm25_incident(
                [t for t in triples if t.source in anchors or t.target in anchors],
                row["text"],
                limit=20,
            )
            result.update(
                {
                    "status": "ok" if outcome.matches else outcome.stop_reason,
                    "mappings": [match.mapping for match in outcome.matches],
                    "pool_triples": [t.__dict__ for t in triples],
                    "candidate_ids": candidates,
                    "b1_evidence": [t.__dict__ for t in b1],
                    "expanded_states": outcome.expanded_states,
                }
            )
        existing[result["id"]] = result
        with output.open("a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"prepared {len(existing)}/{len(rows)} {result['id'][:12]}", flush=True)
    index.close()


def score(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "candidate-pools.jsonl")
    if args.row_limit is not None:
        rows = rows[: args.row_limit]
    encoder = OnnxRelationEncoder()
    relations = {
        value
        for row in rows
        for value in (
            [edge["relation"] for edge in row["graph"]["edges"]]
            + [triple["relation"] for triple in row.get("pool_triples", [])]
        )
    }
    encoder.encode_many(relations)
    results = []
    for row in rows:
        results.append(rerank_row(row, encoder.similarity))
        print(f"scored {len(results)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.out_dir / "reranked.jsonl", results)
    (args.out_dir / "encoder.json").write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "revision": MODEL_REVISION,
                "onnx_sha256": encoder.model_sha256,
                "tokenizer_sha256": encoder.tokenizer_sha256,
                "relation_count": len(encoder.cache),
                "threshold": SIMILARITY_THRESHOLD,
                "path_weight": PATH_WEIGHT,
                "seconds_unix": time.time(),
            },
            indent=2,
        )
        + "\n"
    )


def has_annotated_path(start: str, relations: list[str], evidence: list[dict]) -> bool:
    """Follow one FactKG path constraint using only selected real KG triples."""
    frontier = {start}
    for annotated in relations:
        reverse = annotated.startswith("~")
        relation = annotated.removeprefix("~")
        frontier = {
            triple["source"] if reverse else triple["target"]
            for triple in evidence
            if triple["relation"] == relation
            and (triple["target"] if reverse else triple["source"]) in frontier
        }
        if not frontier:
            return False
    return bool(frontier)


def evaluate(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "reranked.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry for claim, entry in raw.items()}
    arms = ("B1", "B4", "E4")
    path_totals = {arm: [0, 0] for arm in arms}
    nonempty = {arm: 0 for arm in arms}
    audits = []
    for row in rows:
        entry = gold[row["id"]]
        examples = {}
        for arm in arms:
            evidence = row["b1_evidence"] if arm == "B1" else row["arms"][arm]["evidence"]
            nonempty[arm] += bool(evidence)
            covered = total = 0
            if entry["Label"][0]:
                for start, paths in entry.get("Evidence", {}).items():
                    for path in paths:
                        total += 1
                        covered += has_annotated_path(start, path, evidence)
            path_totals[arm][0] += covered
            path_totals[arm][1] += total
            examples[arm] = {"evidence": len(evidence), "covered_paths": covered, "paths": total}
        audits.append(
            {
                "id": row["id"],
                "text": row["text"],
                "gold": entry["Label"][0],
                "query_edges": len(row["graph"]["edges"]),
                "mapping_changed": row["arms"]["B4"].get("mapping")
                != row["arms"]["E4"].get("mapping"),
                "evidence_changed": row["arms"]["B4"]["evidence"] != row["arms"]["E4"]["evidence"],
                "arms": examples,
            }
        )
    summary = {
        "split": args.split,
        "claims": len(rows),
        "eligible_query_edges_ge_2": sum(item["query_edges"] >= 2 for item in audits),
        "query_paths_present": sum(row["arms"]["B4"].get("query_paths", 0) > 0 for row in rows),
        "path_signal_varies_in_top50": sum(
            row.get("top50_complete_path_max", 0) > row.get("top50_complete_path_min", 0)
            for row in rows
        ),
        "mapping_changes": sum(item["mapping_changed"] for item in audits),
        "evidence_changes": sum(item["evidence_changed"] for item in audits),
        "arms": {
            arm: {
                "nonempty_evidence": nonempty[arm],
                "positive_path_constraints_covered": path_totals[arm][0],
                "positive_path_constraints_total": path_totals[arm][1],
            }
            for arm in arms
        },
    }
    write_jsonl(args.out_dir / "retrieval-audit.jsonl", audits)
    (args.out_dir / "retrieval-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def read(args: argparse.Namespace) -> None:
    """Use one frozen KG-only reader and cache identical arm prompts."""
    rows = read_jsonl(args.out_dir / "reranked.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw_gold = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw_gold.items()}
    path = args.out_dir / "predictions.jsonl"
    existing = {row["id"]: row for row in read_jsonl(path)} if path.exists() else {}
    cache: dict[str, tuple[str, dict, float]] = {}
    for row in rows:
        if row["id"] in existing:
            saved = existing[row["id"]]
            if saved["model"] != args.model:
                raise ValueError(f"cached reader used a different model: {row['id']}")
            for arm in ("B1", "B4", "E4"):
                evidence = row["b1_evidence"] if arm == "B1" else row["arms"][arm]["evidence"]
                evidence_sha256 = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode()
                ).hexdigest()
                if saved["arms"][arm]["evidence_sha256"] != evidence_sha256:
                    raise ValueError(f"cached reader used different evidence: {row['id']} {arm}")
            continue
        record = {"id": row["id"], "gold": gold[row["id"]], "model": args.model, "arms": {}}
        for arm in ("B1", "B4", "E4"):
            evidence = row["b1_evidence"] if arm == "B1" else row["arms"][arm]["evidence"]
            evidence_sha256 = hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()
            ).hexdigest()
            verdict, usage, seconds = "UNKNOWN", {}, 0.0
            if evidence:
                key = json.dumps([row["text"], evidence], sort_keys=True)
                if key not in cache:
                    raw, usage, seconds = call_model(
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
                        api_key=api_key_for(args),
                        json_mode=args.json_mode,
                    )
                    try:
                        value = json.loads(raw).get("verdict")
                        verdict = value if value in ("TRUE", "FALSE", "UNKNOWN") else "UNKNOWN"
                    except (ValueError, TypeError, AttributeError):
                        verdict = "UNKNOWN"
                    cache[key] = verdict, usage, seconds
                verdict, usage, seconds = cache[key]
            record["arms"][arm] = {
                "verdict": verdict,
                "evidence_sha256": evidence_sha256,
                "correct": verdict in ("TRUE", "FALSE") and (verdict == "TRUE") == gold[row["id"]],
                "usage": usage,
                "reader_seconds": seconds,
            }
        with path.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing[row["id"]] = record
        print(f"read {len(existing)}/{len(rows)} {row['id'][:12]}", flush=True)
    if set(existing) == {row["id"] for row in rows}:
        summary = {
            "split": args.split,
            "n": len(rows),
            "model": args.model,
            "arms": {
                arm: {
                    "accuracy": sum(record["arms"][arm]["correct"] for record in existing.values())
                    / len(rows),
                    "unknown": sum(
                        record["arms"][arm]["verdict"] == "UNKNOWN" for record in existing.values()
                    ),
                }
                for arm in ("B1", "B4", "E4")
            },
        }
        (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "score", "evaluate", "read"))
    parser.add_argument("--extract-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--kg", type=Path, default=Path("data/factkg/data/dbpedia_2015_undirected_light.pickle")
    )
    parser.add_argument(
        "--name-index", type=Path, default=Path("data/factkg/index/entities-fts.sqlite")
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--kilo-auth-provider")
    parser.add_argument("--json-mode", choices=("object", "schema"), default="object")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    parser.add_argument("--row-limit", type=int)
    args = parser.parse_args()
    if args.row_limit is not None and args.row_limit < 1:
        parser.error("row-limit must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    {"prepare": prepare, "score": score, "evaluate": evaluate, "read": read}[args.phase](args)


if __name__ == "__main__":
    main()
