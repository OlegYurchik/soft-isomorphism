"""Staged FactKG graph retrieval pilot. Inputs are trusted upstream pickle files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pickle
import re
import sqlite3
import time
import unicodedata
import urllib.request
from collections import Counter, deque
from pathlib import Path

from soft_isomorphism.matching import Edge, Node, Triple, _edge_distance, label_distance
from soft_isomorphism.search import beam_search

PROMPTS = [
    "Extract all explicitly asserted subject-relation-object facts from this text.",
    "Read each clause and extract its asserted relations; do not add background knowledge.",
    "Identify entities, then the relations actually asserted between them in this text.",
]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def selected_claims(path: Path, limit: int) -> list[str]:
    with path.open("rb") as stream:
        rows = pickle.load(stream)
    return sorted(rows, key=digest)[:limit]


def norm(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    return " ".join(cleaned.split())


GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
                "required": ["id", "label"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "relation": {"type": "string"},
                    "target": {"type": "string"},
                    "polarity": {"enum": ["positive", "negative"]},
                    "quote": {"type": "string"},
                },
                "required": ["source", "relation", "target", "polarity", "quote"],
            },
        },
    },
    "required": ["nodes", "edges"],
}


def call_model(
    url: str,
    system: str,
    user: str,
    max_tokens: int,
    *,
    schema: dict | None = None,
    model: str = "qwen2.5-7b-instruct-q4-k-m",
    api_key: str | None = None,
    json_mode: str = "schema",
) -> tuple[str, dict, float]:
    if "qwen3" in model.lower() and "qwen3.8" not in model.lower():
        user += "\n/no_think"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "seed": 42,
        "max_tokens": max_tokens,
        "response_format": (
            {"type": "json_schema", "schema": schema}
            if schema and json_mode == "schema"
            else {"type": "json_object"}
        ),
    }
    if "qwen3.8" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.load(response)
    choice = data["choices"][0]
    usage = {**data.get("usage", {}), "finish_reason": choice.get("finish_reason")}
    return choice["message"].get("content") or "", usage, time.perf_counter() - started


def parse_view(
    raw: str, claim: str, allowed_relations: set[str] | None = None
) -> list[tuple[str, str, str, str]]:
    raw = re.sub(r"^\s*```(?:json)?|\s*```\s*$", "", raw.strip(), flags=re.I)
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("nodes"), list)
        or not isinstance(data.get("edges"), list)
    ):
        raise ValueError("expected nodes and edges lists")
    labels = {}
    for node in data["nodes"]:
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), (str, int))
            or not isinstance(node.get("label"), str)
        ):
            raise ValueError("invalid node")
        node_id = str(node["id"])
        label = node["label"]
        if len(node_id) >= 4 and norm(node_id) in norm(claim):
            # Some models use the ID as the surface name and label as a type.
            label = node_id
        if label != "?" and norm(label) not in norm(claim):
            raise ValueError("node has no surface name grounded in the claim")
        labels[node_id] = label
    labels.setdefault("?", "?")
    edges = []
    for edge in data["edges"]:
        if (
            not isinstance(edge, dict)
            or str(edge.get("source")) not in labels
            or str(edge.get("target")) not in labels
        ):
            raise ValueError("invalid edge endpoints")
        if edge.get("polarity") not in ("positive", "negative"):
            raise ValueError("invalid polarity")
        if not isinstance(edge.get("quote"), str) or edge["quote"] not in claim:
            raise ValueError("quote is not an exact substring")
        if not isinstance(edge.get("relation"), str) or not edge["relation"]:
            raise ValueError("missing relation")
        if allowed_relations is not None and edge["relation"] not in allowed_relations | {
            "unknown"
        }:
            raise ValueError("relation is outside the supplied KG vocabulary")
        edges.append(
            (
                norm(labels[str(edge["source"])]),
                norm(edge["relation"]),
                norm(labels[str(edge["target"])]),
                edge["polarity"],
            )
        )
    return edges


def merge_views(views: list[list[tuple[str, str, str, str]]]) -> dict:
    if not views:
        raise ValueError("at least one extraction view is required")
    counts = Counter(edge for view in views for edge in set(view))
    labels = sorted({label for edge in counts for label in (edge[0], edge[2])})
    ids = {label: f"n{i}" for i, label in enumerate(labels)}
    return {
        "nodes": [{"id": ids[label], "label": label} for label in labels],
        "edges": [
            {
                "source": ids[a],
                "relation": r,
                "target": ids[b],
                "polarity": p,
                "confidence": max(0.2, count / len(views)),
            }
            for (a, r, b, p), count in sorted(counts.items())
        ],
    }


def relation_candidates(relations: list[str], claim: str, limit: int = 80) -> list[str]:
    """Deterministically restrict the vocabulary for the CPU feasibility pilot."""
    words = set(re.findall(r"[a-z]+", claim.casefold()))

    def rank(relation: str) -> tuple[int, str]:
        split = re.sub(r"([a-z])([A-Z])", r"\1 \2", relation)
        parts = set(re.findall(r"[a-z]+", split.casefold()))
        overlap = len(words & parts)
        prefix = sum(
            any(word.startswith(part[:4]) for word in words) for part in parts if len(part) >= 4
        )
        return -(overlap * 2 + prefix), relation

    return sorted(relations, key=rank)[:limit]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def prepare(args: argparse.Namespace) -> None:
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    relations = sorted(
        {relation.removeprefix("~") for adjacency in kg.values() for relation in adjacency}
    )
    args.work_dir.mkdir(parents=True, exist_ok=True)
    (args.work_dir / "relations.json").write_text(json.dumps(relations, ensure_ascii=False))
    print(json.dumps({"kg_entities": len(kg), "relations": len(relations)}))


def index_names(args: argparse.Namespace) -> None:
    """Build a reusable lexical index without putting gold annotations in it."""
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    args.name_index.parent.mkdir(parents=True, exist_ok=True)
    if args.name_index.exists():
        raise FileExistsError(f"Name index already exists: {args.name_index}")
    conn = sqlite3.connect(args.name_index)
    conn.execute(
        "CREATE VIRTUAL TABLE entity_names USING fts5(id UNINDEXED, label, tokenize='trigram')"
    )
    batch = []
    for index, kg_id in enumerate(kg, start=1):
        batch.append((kg_id, norm(kg_id)))
        if len(batch) == 100_000:
            conn.executemany("INSERT INTO entity_names(id,label) VALUES(?,?)", batch)
            conn.commit()
            batch.clear()
            print(f"indexed {index}/{len(kg)}", flush=True)
    if batch:
        conn.executemany("INSERT INTO entity_names(id,label) VALUES(?,?)", batch)
        conn.commit()
    conn.close()
    print(json.dumps({"indexed_entities": len(kg), "index": str(args.name_index)}))


def link_candidates(index: sqlite3.Connection, label: str, limit: int = 5) -> list[str]:
    cleaned = norm(label).replace('"', "")
    if len(cleaned) < 3:
        return []
    words = re.findall(r"[\w-]+", cleaned)
    if not words:
        return []
    queries = ['"' + cleaned + '"', '"' + max(words, key=len) + '"']
    if len(words) > 1 and 4 <= len(words[0]) <= 6:
        queries.append('"' + words[0] + '"')
    hits: set[str] = set()
    for query in queries:
        try:
            rows = index.execute(
                "SELECT id FROM entity_names WHERE label MATCH ? "
                "ORDER BY bm25(entity_names) LIMIT 500",
                (query,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        hits.update(row[0] for row in rows)
    ranked = sorted(hits, key=lambda kg_id: (label_distance(label, kg_id.replace("_", " ")), kg_id))
    return [kg_id for kg_id in ranked[:limit] if label_distance(label, kg_id.replace("_", " ")) < 1]


def direct_id_variants(label: str, kg: dict) -> list[str]:
    """Prefer exact KG identifiers, including a leading-article variant."""
    stripped = re.sub(r"^(?:the|a|an)\s+", "", label, flags=re.I)
    candidates = [
        value.replace(" ", "_")
        for phrase in (label, stripped)
        for value in (phrase, phrase.title())
    ]
    return list(dict.fromkeys(identifier for identifier in candidates if identifier in kg))


def variable_candidates(
    node_id: str, graph: dict, triples: list[Triple], anchors: dict[str, list[str]], seeds: set[str]
) -> list[str]:
    """Rank unnamed nodes by edges connecting them to named query anchors."""
    scores: dict[str, float] = {}
    for edge in graph["edges"]:
        if node_id not in (edge["source"], edge["target"]):
            continue
        other_id = edge["target"] if edge["source"] == node_id else edge["source"]
        other_anchors = set(anchors.get(other_id, []))
        for triple in triples:
            if edge["target"] == node_id and triple.source in other_anchors:
                candidate = triple.target
            elif edge["source"] == node_id and triple.target in other_anchors:
                candidate = triple.source
            else:
                continue
            if not candidate or candidate in seeds or candidate.startswith('"'):
                continue
            score = 1 - _edge_distance(edge["relation"], triple.relation)
            scores[candidate] = max(scores.get(candidate, -1), score)
    ranked = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))
    return ranked[:20]


def api_key_for(args: argparse.Namespace) -> str | None:
    if args.kilo_auth_provider:
        path = Path.home() / ".local/share/kilo/auth.json"
        return json.loads(path.read_text())[args.kilo_auth_provider]["key"]
    return os.getenv(args.api_key_env)


def extract(args: argparse.Namespace) -> None:
    claims = selected_claims(args.data_dir / f"factkg_{args.split}.pickle", args.limit)
    relations = json.loads((args.work_dir / "relations.json").read_text())
    output = args.work_dir / "extract.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    for row in existing.values():
        if (
            row.get("extract_model") != args.model
            or row.get("extract_views") != args.extract_views
            or row.get("relation_limit") != args.relation_limit
            or row.get("open_relations", False) != args.open_relations
        ):
            raise ValueError("cached extraction has different model or extraction settings")
    for claim in claims:
        identifier = digest(claim)
        if identifier in existing:
            continue
        views, raw_views, usage = [], [], []
        relevant_relations = (
            []
            if args.open_relations
            else relation_candidates(relations, claim, args.relation_limit)
        )
        for instruction in PROMPTS[: args.extract_views]:
            raw, tokens, seconds = call_model(
                args.server_url,
                "Return one JSON object only. Do not decide whether the claim is true. "
                "Use local node IDs. Copy named entity labels literally from the claim; "
                "never replace a name by a generic class like Person or Award. "
                "Use '?' only for an unspecified entity. "
                "Polarity must be positive or negative. "
                "Every quote must be an exact substring of the claim.",
                instruction
                + (
                    "\nUse a concise relation phrase from the claim."
                    if args.open_relations
                    else "\nAllowed relation labels (choose one or 'unknown'): "
                    + ", ".join(relevant_relations)
                )
                + "\nClaim: "
                + claim
                + "\nSchema: {nodes:[{id,label}],edges:[{source,relation,target,polarity,quote}]}",
                args.extract_max_tokens,
                schema=GRAPH_SCHEMA,
                model=args.model,
                api_key=api_key_for(args),
                json_mode=args.json_mode,
            )
            raw_views.append(raw)
            usage.append({"tokens": tokens, "seconds": seconds})
            try:
                views.append(
                    parse_view(raw, claim, None if args.open_relations else set(relevant_relations))
                )
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                views.append([])
        row = {
            "id": identifier,
            "text": claim,
            "graph": merge_views(views),
            "allowed_relations": relevant_relations,
            "extract_model": args.model,
            "extract_views": args.extract_views,
            "relation_limit": args.relation_limit,
            "open_relations": args.open_relations,
            "valid_views": sum(bool(view) for view in views),
            "raw_views": raw_views,
            "usage": usage,
        }
        existing[identifier] = row
        write_jsonl(output, [existing[digest(text)] for text in claims if digest(text) in existing])
        edge_count = len(row["graph"]["edges"])
        print(
            f"extracted {len(existing)}/{len(claims)} {identifier[:12]} edges={edge_count}",
            flush=True,
        )


def reparse(args: argparse.Namespace) -> None:
    path = args.work_dir / "extract.jsonl"
    rows = read_jsonl(path)
    for row in rows:
        views = []
        for raw in row["raw_views"]:
            try:
                views.append(
                    parse_view(
                        raw,
                        row["text"],
                        None if row.get("open_relations") else set(row["allowed_relations"]),
                    )
                )
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                views.append([])
        row["graph"] = merge_views(views)
        row["valid_views"] = sum(bool(view) for view in views)
    write_jsonl(path, rows)
    print(json.dumps({"claims": len(rows), "valid_views": sum(row["valid_views"] for row in rows)}))


def kg_triples(kg: dict, head: str) -> list[Triple]:
    result = []
    for relation, tails in kg.get(head, {}).items():
        for tail in tails:
            if relation.startswith("~"):
                result.append(Triple(tail, relation[1:], head))
            else:
                result.append(Triple(head, relation, tail))
    return result


def bm25_incident(triples: list[Triple], claim: str, limit: int = 30) -> list[Triple]:
    """Rank incident KG triples by BM25 against the raw claim."""

    def tokens(value: str) -> list[str]:
        split = re.sub(r"([a-z])([A-Z])", r"\1 \2", value.replace("_", " "))
        return re.findall(r"[a-z0-9]+", split.casefold())

    query = set(tokens(claim))
    documents = [Counter(tokens(" ".join((t.source, t.relation, t.target)))) for t in triples]
    lengths = [sum(doc.values()) for doc in documents]
    average = sum(lengths) / len(lengths) if lengths else 1
    frequencies = Counter(term for doc in documents for term in doc)

    def score(index: int) -> float:
        total = 0.0
        for term in query:
            tf = documents[index][term]
            if not tf:
                continue
            df = frequencies[term]
            idf = math.log(1 + (len(triples) - df + 0.5) / (df + 0.5))
            total += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * lengths[index] / average))
        return total

    order = sorted(
        range(len(triples)),
        key=lambda i: (-score(i), triples[i].source, triples[i].relation, triples[i].target),
    )
    return [triples[i] for i in order[:limit]]


def candidate_pool(
    kg: dict, graph: dict, claim: str, name_index: sqlite3.Connection | None = None
) -> tuple[dict[str, Node], list[Triple], dict[str, list[str]]]:
    anchors = {}
    for node in graph["nodes"]:
        label = node["label"]
        if label == "?":
            continue
        if name_index is not None:
            direct = direct_id_variants(label, kg)
            fuzzy = [id for id in link_candidates(name_index, label) if id in kg]
            anchors[node["id"]] = list(dict.fromkeys([*direct, *fuzzy]))[:5]
        else:
            anchors[node["id"]] = direct_id_variants(label, kg)[:5] or [None]
    if name_index is None:
        unresolved = {
            norm(node["label"]): node["id"]
            for node in graph["nodes"]
            if node["label"] != "?" and not anchors[node["id"]][0]
        }
        if unresolved:
            for kg_id in kg:
                key = norm(kg_id)
                if key in unresolved:
                    anchors[unresolved.pop(key)] = [kg_id]
                    if not unresolved:
                        break
    seeds = sorted({value for values in anchors.values() for value in values if value})
    if not seeds:
        return {}, [], {node["id"]: [] for node in graph["nodes"]}
    frontier = deque((seed, 0) for seed in seeds)
    visited = set(seeds)
    triples: dict[tuple[str, str, str], Triple] = {}
    while frontier and len(triples) < 2000:
        head, depth = frontier.popleft()
        if depth >= 2:
            continue
        incident = bm25_incident(kg_triples(kg, head), claim)
        for triple in incident:
            triples[(triple.source, triple.relation, triple.target)] = triple
            other = triple.target if triple.source == head else triple.source
            if other not in visited:
                visited.add(other)
                frontier.append((other, depth + 1))
            if len(triples) >= 2000:
                break
    values = list(triples.values())
    nodes = {
        identifier: Node(identifier, identifier.replace("_", " "))
        for triple in values
        for identifier in (triple.source, triple.target)
    }
    for seed in seeds:
        nodes.setdefault(seed, Node(seed, seed.replace("_", " ")))
    candidates = {}
    for node in graph["nodes"]:
        if node["label"] == "?":
            linked = variable_candidates(node["id"], graph, values, anchors, set(seeds))
            fallback = [
                identifier
                for identifier in sorted(nodes)
                if identifier
                and identifier != "?"
                and identifier not in seeds
                and not identifier.startswith('"')
            ]
            candidates[node["id"]] = list(dict.fromkeys([*linked, *fallback]))[:20]
        else:
            candidates[node["id"]] = [value for value in anchors.get(node["id"], []) if value]
    return nodes, values, candidates


def evidence(
    mapping: dict[str, str | None],
    graph: dict,
    triples: list[Triple],
    *,
    counterevidence: bool = False,
    weighted: bool = True,
) -> list[dict]:
    by_pair: dict[tuple[str, str], list[Triple]] = {}
    by_source: dict[str, list[Triple]] = {}
    for triple in triples:
        by_pair.setdefault((triple.source, triple.target), []).append(triple)
        by_source.setdefault(triple.source, []).append(triple)
    result = []
    for edge in sorted(graph["edges"], key=lambda e: -e["confidence"] if weighted else 0):
        source, target = mapping.get(edge["source"]), mapping.get(edge["target"])
        if source is None:
            continue
        choices = by_pair.get((source, target), []) if target is not None else []
        if choices:
            best = min(
                choices, key=lambda t: (_edge_distance(edge["relation"], t.relation), t.relation)
            )
            item = {"source": best.source, "relation": best.relation, "target": best.target}
            if item not in result:
                result.append(item)
        if counterevidence and (
            not choices or min(_edge_distance(edge["relation"], t.relation) for t in choices) > 0
        ):
            alternatives = sorted(
                (
                    triple
                    for triple in by_source.get(source, [])
                    if triple.target != target
                    and _edge_distance(edge["relation"], triple.relation) == 0
                ),
                key=lambda t: (t.relation, t.target),
            )
            for triple in alternatives[:3]:
                item = {
                    "source": triple.source,
                    "relation": triple.relation,
                    "target": triple.target,
                }
                if item not in result:
                    result.append(item)
        if len(result) >= 20:
            break
    return result[:20]


def expanded_evidence(
    kg: dict, mapping: dict[str, str | None], graph: dict, *, limit: int = 20
) -> list[dict]:
    """Return real KG facts near mapped endpoints, including reverse and alternate values."""
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    found: dict[tuple[str, str, str], tuple[float, Triple]] = {}
    for edge in graph["edges"]:
        source, target = mapping.get(edge["source"]), mapping.get(edge["target"])
        if source is None:
            continue
        incident = kg_triples(kg, source)
        relation = edge["relation"]
        relevant = []
        for triple in incident:
            direct = target is not None and {triple.source, triple.target} == {source, target}
            relation_score = 1 - _edge_distance(relation, triple.relation)
            if not direct and relation_score < 0.5:
                continue
            target_score = 1 - label_distance(
                labels[edge["target"]], triple.target.replace("_", " ")
            )
            score = (2 if direct else 0) + relation_score + 0.25 * target_score
            relevant.append((score, triple))
        for score, triple in sorted(
            relevant, key=lambda x: (-x[0], x[1].source, x[1].relation, x[1].target)
        )[:3]:
            key = triple.source, triple.relation, triple.target
            if key not in found or score > found[key][0]:
                found[key] = score, triple
    ranked = sorted(found.values(), key=lambda x: (-x[0], x[1].source, x[1].relation, x[1].target))
    return [
        {"source": triple.source, "relation": triple.relation, "target": triple.target}
        for _, triple in ranked[:limit]
    ]


def match(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.work_dir / "extract.jsonl")
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    name_index = sqlite3.connect(args.name_index) if args.name_index.exists() else None
    if name_index is not None:
        indexed = name_index.execute("SELECT count(*) FROM entity_names").fetchone()[0]
        if indexed != len(kg):
            raise ValueError(f"Incomplete KG name index: {indexed} of {len(kg)} entities")
    output = []
    for row in rows:
        graph = row["graph"]
        result = {
            "id": row["id"],
            "text": row["text"],
            "graph": graph,
            "evidence_mode": args.evidence_mode,
            "arms": {},
        }
        if graph["nodes"] and graph["edges"]:
            pool_nodes, pool_edges, candidates = candidate_pool(kg, graph, row["text"], name_index)
            result["candidate_ids"] = candidates
            query_nodes = [Node(item["id"], item["label"]) for item in graph["nodes"]]
            for arm in ("B3", "E1"):
                query_edges = [
                    Edge(
                        item["source"],
                        item["relation"],
                        item["target"],
                        item["confidence"] if arm == "E1" else 1.0,
                    )
                    for item in graph["edges"]
                ]
                outcome = beam_search(query_nodes, query_edges, pool_nodes, pool_edges, candidates)
                best = outcome.matches[0] if outcome.matches else None
                strict = (
                    evidence(best.mapping, graph, pool_edges, weighted=arm == "E1") if best else []
                )
                selected_evidence = (
                    expanded_evidence(kg, best.mapping, graph)
                    if best and args.evidence_mode == "expanded"
                    else (
                        evidence(
                            best.mapping,
                            graph,
                            pool_edges,
                            counterevidence=True,
                            weighted=arm == "E1",
                        )
                        if best and args.counterevidence
                        else strict
                    )
                )
                result["arms"][arm] = {
                    "status": outcome.stop_reason if best is None else "ok",
                    "cost": best.total_cost if best else None,
                    "mapping": best.mapping if best else None,
                    "strict_evidence": strict,
                    "evidence": selected_evidence,
                    "expanded_states": outcome.expanded_states,
                    "seconds": outcome.elapsed_seconds,
                    "optimal_within_candidates": outcome.optimal_within_candidates,
                    "pool_edges": len(pool_edges),
                    "linked_nodes": sum(bool(ids) for ids in candidates.values()),
                }
        else:
            result["arms"] = {
                arm: {"status": "empty_graph", "evidence": []} for arm in ("B3", "E1")
            }
        output.append(result)
        print(f"matched {len(output)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.work_dir / "match.jsonl", output)
    if name_index is not None:
        name_index.close()


def refresh_evidence(args: argparse.Namespace) -> None:
    """Recompute retrieval context from saved mappings without repeating graph search."""
    path = args.work_dir / "match.jsonl"
    rows = read_jsonl(path)
    with args.kg.open("rb") as stream:
        kg = pickle.load(stream)
    for row in rows:
        row["evidence_mode"] = args.evidence_mode
        for arm in ("B3", "E1"):
            outcome = row["arms"][arm]
            if outcome.get("mapping") and args.evidence_mode == "expanded":
                outcome["evidence"] = expanded_evidence(kg, outcome["mapping"], row["graph"])
            else:
                outcome["evidence"] = outcome.get("strict_evidence", [])
    write_jsonl(path, rows)
    print(json.dumps({"claims": len(rows), "evidence_mode": args.evidence_mode}))


def read(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.work_dir / "match.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        gold = {digest(claim): entry["Label"][0] for claim, entry in pickle.load(stream).items()}
    cache = {}
    output = []
    for row in rows:
        record = {"id": row["id"], "gold": gold[row["id"]], "arms": {}}
        for arm in ("B3", "E1"):
            method = row["arms"][arm]
            verdict, usage, seconds = "UNKNOWN", {}, 0.0
            if method["status"] == "ok" and method["evidence"]:
                key = json.dumps([row["text"], method["evidence"]], sort_keys=True)
                if key not in cache:
                    raw, usage, seconds = call_model(
                        args.server_url,
                        "Return one JSON object only with verdict TRUE, FALSE or UNKNOWN. "
                        "Use only the supplied KG triples. "
                        "Missing evidence alone is not proof of falsehood.",
                        "Claim: "
                        + row["text"]
                        + "\nKG triples: "
                        + json.dumps(method["evidence"], ensure_ascii=False)
                        + '\nReturn {"verdict":"TRUE|FALSE|UNKNOWN"}.',
                        args.reader_max_tokens,
                        model=args.model,
                        api_key=api_key_for(args),
                        json_mode=args.json_mode,
                    )
                    try:
                        parsed = json.loads(raw)
                        if parsed.get("verdict") in ("TRUE", "FALSE", "UNKNOWN"):
                            verdict = parsed["verdict"]
                    except (ValueError, TypeError, AttributeError):
                        pass
                    cache[key] = (verdict, usage, seconds)
                verdict, usage, seconds = cache[key]
            record["arms"][arm] = {
                "verdict": verdict,
                "correct": verdict in ("TRUE", "FALSE") and (verdict == "TRUE") == gold[row["id"]],
                "usage": usage,
                "reader_seconds": seconds,
            }
        output.append(record)
        write_jsonl(args.work_dir / "predictions.jsonl", output)
        print(f"read {len(output)}/{len(rows)} {row['id'][:12]}", flush=True)
    summary = {
        "n": len(output),
        "split": args.split,
        "selection": "first N by SHA256 claim",
        "model": args.model,
        "evidence_mode": rows[0].get("evidence_mode", "strict") if rows else None,
        "arms": {
            arm: {
                "accuracy": sum(item["arms"][arm]["correct"] for item in output) / len(output),
                "unknown": sum(item["arms"][arm]["verdict"] == "UNKNOWN" for item in output),
            }
            for arm in ("B3", "E1")
        },
    }
    (args.work_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def fallback_verdict(graph_verdict: str, b0_prediction: bool) -> tuple[str, str]:
    if graph_verdict == "UNKNOWN":
        return ("TRUE" if b0_prediction else "FALSE"), "B0"
    if graph_verdict in ("TRUE", "FALSE"):
        return graph_verdict, "graph"
    raise ValueError(f"invalid graph verdict: {graph_verdict}")


def hybrid(args: argparse.Namespace) -> None:
    """Evaluate a separately labelled B0 fallback on the same saved claims."""
    baseline = json.loads(args.b0_file.read_text())
    if baseline["split"] != args.split:
        raise ValueError("B0 and graph predictions use different splits")
    b0 = {row["id"]: row["prediction"] for row in baseline["predictions"]}
    if not all(type(value) is bool for value in b0.values()):
        raise ValueError("B0 predictions must be booleans")
    rows = read_jsonl(args.work_dir / "predictions.jsonl")
    if not rows:
        raise ValueError("no graph predictions to combine")
    output = []
    for row in rows:
        if row["id"] not in b0:
            raise ValueError(f"missing B0 prediction for {row['id']}")
        record = {"id": row["id"], "gold": row["gold"], "b0": b0[row["id"]], "arms": {}}
        for arm in ("B3", "E1"):
            verdict, source = fallback_verdict(row["arms"][arm]["verdict"], b0[row["id"]])
            record["arms"][arm] = {
                "verdict": verdict,
                "source": source,
                "correct": (verdict == "TRUE") == row["gold"],
            }
        output.append(record)
    write_jsonl(args.work_dir / "hybrid.jsonl", output)
    summary = {
        "n": len(output),
        "split": args.split,
        "b0_method": baseline.get("method"),
        "b0_file_sha256": hashlib.sha256(args.b0_file.read_bytes()).hexdigest(),
        "b0_accuracy": sum(row["b0"] == row["gold"] for row in output) / len(output),
        "arms": {
            arm: {
                "accuracy": sum(row["arms"][arm]["correct"] for row in output) / len(output),
                "unknown": 0,
                "b0_fallbacks": sum(row["arms"][arm]["source"] == "B0" for row in output),
            }
            for arm in ("B3", "E1")
        },
    }
    (args.work_dir / "hybrid-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "prepare",
            "index",
            "extract",
            "reparse",
            "match",
            "refresh-evidence",
            "read",
            "hybrid",
        ),
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument(
        "--kg", type=Path, default=Path("data/factkg/data/dbpedia_2015_undirected_light.pickle")
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument(
        "--name-index", type=Path, default=Path("data/factkg/index/entities-fts.sqlite")
    )
    parser.add_argument("--split", choices=("train", "dev", "test"), default="train")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--server-url", default="http://127.0.0.1:8997")
    parser.add_argument("--model", default="qwen2.5-7b-instruct-q4-k-m")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--kilo-auth-provider")
    parser.add_argument("--json-mode", choices=("schema", "object"), default="schema")
    parser.add_argument("--extract-max-tokens", type=int, default=256)
    parser.add_argument("--extract-views", type=int, choices=(1, 3), default=3)
    parser.add_argument("--relation-limit", type=int, default=80)
    parser.add_argument("--open-relations", action="store_true")
    parser.add_argument("--reader-max-tokens", type=int, default=128)
    parser.add_argument("--counterevidence", action="store_true")
    parser.add_argument("--evidence-mode", choices=("strict", "expanded"), default="strict")
    parser.add_argument("--b0-file", type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit must be positive")
    if args.relation_limit < 1:
        parser.error("relation-limit must be positive")
    if args.phase == "hybrid" and args.b0_file is None:
        parser.error("hybrid requires --b0-file")
    {
        "prepare": prepare,
        "index": index_names,
        "extract": extract,
        "reparse": reparse,
        "match": match,
        "refresh-evidence": refresh_evidence,
        "read": read,
        "hybrid": hybrid,
    }[args.phase](args)


if __name__ == "__main__":
    main()
