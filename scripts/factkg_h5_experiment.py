"""H5 diagnostic: add connected KG paths as a residual over lexical B1."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import re
from collections import defaultdict
from pathlib import Path

from factkg_e1_pilot import api_key_for, call_model, digest, read_jsonl, write_jsonl
from factkg_e4_experiment import OnnxRelationEncoder, has_annotated_path, relation_text

MAX_HOPS = 3
FANOUT = 16
BEAM = 64
BASE_KEEP = 12
EVIDENCE_BUDGET = 20
ARMS = ("B1", "Flat", "H5")


def triple_key(triple: dict) -> tuple[str, str, str]:
    return triple["source"], triple["relation"], triple["target"]


def tokens(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").casefold()
    return set(re.findall(r"[a-z0-9]+", text))


def lexical_score(claim: str, text: str) -> float:
    left, right = tokens(claim), tokens(text)
    return len(left & right) / math.sqrt(max(1, len(left) * len(right)))


def arc_text(source: str, relation: str, target: str) -> str:
    if relation.startswith("~"):
        return (
            f"{source.replace('_', ' ')} inverse {relation_text(relation)} "
            f"{target.replace('_', ' ')}"
        )
    return f"{source.replace('_', ' ')} {relation_text(relation)} {target.replace('_', ' ')}"


def path_text(path: tuple[dict, ...]) -> str:
    parts = [path[0]["source"].replace("_", " ")]
    for arc in path:
        relation = relation_text(arc["relation"])
        if arc["relation"].startswith("~"):
            relation = "inverse " + relation
        parts.extend((relation, arc["target"].replace("_", " ")))
    return " ; ".join(parts)


def path_evidence(path: tuple[dict, ...]) -> list[dict]:
    evidence = []
    for arc in path:
        triple = arc["evidence"]
        if triple not in evidence:
            evidence.append(triple)
    return evidence


def build_arcs(triples: list[dict]) -> dict[str, list[dict]]:
    adjacency: dict[str, list[dict]] = defaultdict(list)
    for triple in triples:
        adjacency[triple["source"]].append(
            {
                "source": triple["source"],
                "relation": triple["relation"],
                "target": triple["target"],
                "evidence": triple,
            }
        )
        adjacency[triple["target"]].append(
            {
                "source": triple["target"],
                "relation": "~" + triple["relation"],
                "target": triple["source"],
                "evidence": triple,
            }
        )
    return adjacency


def enumerate_paths(row: dict) -> list[tuple[dict, ...]]:
    """Bounded simple paths from linked entity candidates, without labels or gold."""
    adjacency = build_arcs(row["pool_triples"])
    anchors = sorted(
        {
            identifier
            for identifiers in row.get("candidate_ids", {}).values()
            for identifier in identifiers
            if identifier in adjacency
        }
    )
    found: dict[tuple[tuple[str, str, str], ...], tuple[dict, ...]] = {}
    for start in anchors:
        beam: list[tuple[dict, ...]] = [()]
        for depth in range(1, MAX_HOPS + 1):
            expanded = []
            for path in beam:
                node = start if not path else path[-1]["target"]
                used = {start, *(arc["target"] for arc in path)}
                choices = sorted(
                    (arc for arc in adjacency.get(node, []) if arc["target"] not in used),
                    key=lambda arc: (
                        -lexical_score(row["text"], arc_text(node, arc["relation"], arc["target"])),
                        arc["relation"],
                        arc["target"],
                    ),
                )[:FANOUT]
                expanded.extend((*path, arc) for arc in choices)
            beam = sorted(
                expanded,
                key=lambda path: (
                    -lexical_score(row["text"], path_text(path)),
                    tuple((arc["relation"], arc["target"]) for arc in path),
                ),
            )[:BEAM]
            if depth >= 2:
                for path in beam:
                    key = tuple((arc["source"], arc["relation"], arc["target"]) for arc in path)
                    found.setdefault(key, path)
    return list(found.values())


def merge_with_b1(b1: list[dict], additions: list[list[dict]]) -> list[dict]:
    """Keep the B1 head, add complete units, then restore the B1 tail."""
    selected = list(b1[:BASE_KEEP])
    for unit in additions:
        new = [triple for triple in unit if triple not in selected]
        if new and len(selected) + len(new) <= EVIDENCE_BUDGET:
            selected.extend(new)
        if len(selected) == EVIDENCE_BUDGET:
            break
    for triple in b1[BASE_KEEP:]:
        if triple not in selected and len(selected) < EVIDENCE_BUDGET:
            selected.append(triple)
    return selected


def score_row(row: dict, encoder: OnnxRelationEncoder) -> dict:
    b1 = row.get("b1_evidence", [])
    if row.get("status") != "ok" or not b1:
        return {
            "id": row["id"],
            "text": row["text"],
            "arms": {arm: {"evidence": b1} for arm in ARMS},
            "paths_considered": 0,
            "gate": None,
        }
    paths = enumerate_paths(row)
    b1_texts = [arc_text(t["source"], t["relation"], t["target"]) for t in b1]
    candidate_texts = [path_text(path) for path in paths]
    encoder.encode_many({row["text"], *b1_texts, *candidate_texts})
    b1_scores = sorted(encoder.similarity(row["text"], text) for text in b1_texts)
    gate = b1_scores[len(b1_scores) // 2]
    ranked_paths = sorted(
        (
            (encoder.similarity(row["text"], text), text, path)
            for text, path in zip(candidate_texts, paths, strict=True)
        ),
        key=lambda item: (-item[0], item[1]),
    )
    admitted = [item for item in ranked_paths if item[0] >= gate]
    flat: dict[tuple[str, str, str], tuple[float, dict]] = {}
    for _, _, path in admitted:
        for triple in path_evidence(path):
            text = arc_text(triple["source"], triple["relation"], triple["target"])
            score = encoder.similarity(row["text"], text)
            key = triple_key(triple)
            if key not in flat or score > flat[key][0]:
                flat[key] = score, triple
    ranked_flat = sorted(flat.values(), key=lambda x: (-x[0], triple_key(x[1])))
    flat_units = [[triple] for _, triple in ranked_flat]
    path_units = [path_evidence(path) for _, _, path in admitted]
    flat_evidence = merge_with_b1(b1, flat_units)
    h5_evidence = merge_with_b1(b1, path_units)
    selected_paths = []
    selected_keys = {triple_key(t) for t in h5_evidence[BASE_KEEP:] if t not in b1[BASE_KEEP:]}
    for score, text, path in admitted:
        keys = {triple_key(t) for t in path_evidence(path)}
        if keys & selected_keys:
            selected_paths.append({"score": score, "text": text, "length": len(path)})
    return {
        "id": row["id"],
        "text": row["text"],
        "arms": {
            "B1": {"evidence": b1},
            "Flat": {"evidence": flat_evidence},
            "H5": {"evidence": h5_evidence},
        },
        "paths_considered": len(paths),
        "paths_admitted": len(admitted),
        "gate": gate,
        "selected_paths": selected_paths[:20],
    }


def score(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.candidate_file)
    encoder = OnnxRelationEncoder()
    results = []
    for row in rows:
        results.append(score_row(row, encoder))
        print(f"scored {len(results)}/{len(rows)} {row['id'][:12]}", flush=True)
    write_jsonl(args.out_dir / "retrieval.jsonl", results)


def evaluate(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry for claim, entry in raw.items()}
    totals = {arm: [0, 0] for arm in ARMS}
    audits = []
    for row in rows:
        entry = gold[row["id"]]
        arm_audit = {}
        for arm in ARMS:
            evidence = row["arms"][arm]["evidence"]
            covered = total = 0
            if entry["Label"][0]:
                for start, paths in entry.get("Evidence", {}).items():
                    for path in paths:
                        total += 1
                        covered += has_annotated_path(start, path, evidence)
            totals[arm][0] += covered
            totals[arm][1] += total
            arm_audit[arm] = {"covered_paths": covered, "paths": total, "evidence": len(evidence)}
        audits.append(
            {
                "id": row["id"],
                "text": row["text"],
                "gold": entry["Label"][0],
                "changed_flat": row["arms"]["Flat"]["evidence"] != row["arms"]["B1"]["evidence"],
                "changed_h5": row["arms"]["H5"]["evidence"] != row["arms"]["B1"]["evidence"],
                "arms": arm_audit,
            }
        )
    summary = {
        "split": args.split,
        "claims": len(rows),
        "changed_flat": sum(item["changed_flat"] for item in audits),
        "changed_h5": sum(item["changed_h5"] for item in audits),
        "arms": {
            arm: {
                "covered_paths": totals[arm][0],
                "total_paths": totals[arm][1],
                "path_coverage": totals[arm][0] / totals[arm][1] if totals[arm][1] else None,
            }
            for arm in ARMS
        },
    }
    write_jsonl(args.out_dir / "retrieval-audit.jsonl", audits)
    (args.out_dir / "retrieval-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def read(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.out_dir / "retrieval.jsonl")
    with (args.data_dir / f"factkg_{args.split}.pickle").open("rb") as stream:
        raw = pickle.load(stream)
    gold = {digest(claim): entry["Label"][0] for claim, entry in raw.items()}
    output = args.out_dir / "predictions.jsonl"
    existing = {row["id"]: row for row in read_jsonl(output)} if output.exists() else {}
    cache: dict[str, tuple[str, dict, float]] = {}
    for row in rows:
        if row["id"] in existing:
            saved = existing[row["id"]]
            if saved["model"] != args.model:
                raise ValueError(f"cached reader used a different model: {row['id']}")
            for arm in ARMS:
                evidence = row["arms"][arm]["evidence"]
                evidence_hash = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode()
                ).hexdigest()
                if saved["arms"][arm]["evidence_sha256"] != evidence_hash:
                    raise ValueError(f"cached reader used different evidence: {row['id']} {arm}")
            continue
        record = {"id": row["id"], "gold": gold[row["id"]], "model": args.model, "arms": {}}
        for arm in ARMS:
            evidence = row["arms"][arm]["evidence"]
            evidence_hash = hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()
            ).hexdigest()
            key = json.dumps([row["text"], evidence], sort_keys=True)
            if key not in cache:
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
                    api_key=api_key_for(args),
                    json_mode="object",
                )
                try:
                    value = json.loads(raw_answer).get("verdict")
                    verdict = value if value in ("TRUE", "FALSE", "UNKNOWN") else "UNKNOWN"
                except (ValueError, TypeError, AttributeError):
                    verdict = "UNKNOWN"
                cache[key] = verdict, usage, seconds
            verdict, usage, seconds = cache[key]
            record["arms"][arm] = {
                "verdict": verdict,
                "evidence_sha256": evidence_hash,
                "correct": verdict in ("TRUE", "FALSE") and (verdict == "TRUE") == gold[row["id"]],
                "usage": usage,
                "reader_seconds": seconds,
            }
        with output.open("a") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        existing[row["id"]] = record
        print(f"read {len(existing)}/{len(rows)} {row['id'][:12]}", flush=True)
    summary = {
        "split": args.split,
        "claims": len(rows),
        "model": args.model,
        "arms": {
            arm: {
                "accuracy": sum(row["arms"][arm]["correct"] for row in existing.values())
                / len(rows),
                "unknown": sum(
                    row["arms"][arm]["verdict"] == "UNKNOWN" for row in existing.values()
                ),
            }
            for arm in ARMS
        },
    }
    (args.out_dir / "reader-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("score", "evaluate", "read"))
    parser.add_argument("--candidate-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/factkg/data/factkg_unzip"))
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--server-url", default="https://api.duckduck.cloud")
    parser.add_argument("--model", default="iairlab/qwen3.8-27b")
    parser.add_argument("--kilo-auth-provider", default="itmo_lab")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--reader-max-tokens", type=int, default=256)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    {"score": score, "evaluate": evaluate, "read": read}[args.phase](args)


if __name__ == "__main__":
    main()
