"""Claim-only BM25 nearest-neighbour baseline. Input pickles must be trusted.

No graph, test evidence, or evaluation label enters retrieval. This is a cheap
fact-verification control, not a graph retrieval or SimGRAG reproduction.
"""

import argparse
import hashlib
import heapq
import json
import math
import pickle
import platform
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

STOP = set(
    (
        "a an the is are was were be been being of to in on at by for with and or that "
        "this it as from has have had"
    ).split()
)


def tokens(text):
    # Retain negation: dropping 'not' would change the verification task.
    return [x for x in re.findall(r"[a-z0-9]+", text.lower()) if x not in STOP]


def identifier(text):
    return hashlib.sha256(text.encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    with path.open("rb") as stream:
        data = pickle.load(stream)
    return sorted(data.items(), key=lambda item: identifier(item[0]))


def evaluate(predictions):
    if not predictions:
        raise ValueError("cannot evaluate an empty split")
    correct = sum(r["prediction"] == r["gold"] for r in predictions)
    f1s = []
    for label in (False, True):
        tp = sum(r["prediction"] == label and r["gold"] == label for r in predictions)
        fp = sum(r["prediction"] == label and r["gold"] != label for r in predictions)
        fn = sum(r["prediction"] != label and r["gold"] == label for r in predictions)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return {"n": len(predictions), "accuracy": correct / len(predictions), "macro_f1": sum(f1s) / 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--limit", type=int, default=500, help="0 means entire split")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("limit must be non-negative")
    started = time.perf_counter()
    train_path = args.data_dir / "factkg_train.pickle"
    eval_path = args.data_dir / f"factkg_{args.split}.pickle"
    train = load(train_path)
    evaluation = load(eval_path)
    if args.limit:
        evaluation = evaluation[: args.limit]
    train_ids = {identifier(text) for text, _ in train}
    overlap = sum(identifier(text) in train_ids for text, _ in evaluation)
    # Preserve the official split; additionally report metrics without exact overlaps.
    postings = defaultdict(list)
    lengths = []
    for i, (text, _) in enumerate(train):
        counts = Counter(tokens(text))
        lengths.append(sum(counts.values()))
        for term, count in counts.items():
            postings[term].append((i, count))
    avg_len = sum(lengths) / len(lengths)
    majority = sum(bool(v["Label"][0]) for _, v in train) > len(train) / 2
    predictions = []
    retrieval_seconds = []
    for text, gold_record in evaluation:
        tick = time.perf_counter()
        scores = defaultdict(float)
        for term in set(tokens(text)):
            hits = postings.get(term, [])
            idf = math.log(1 + (len(train) - len(hits) + 0.5) / (len(hits) + 0.5))
            for i, count in hits:
                norm = 1.5 * (0.25 + 0.75 * lengths[i] / avg_len)
                scores[i] += idf * count * 2.5 / (count + norm)
        top = heapq.nsmallest(5, scores, key=lambda i: (-scores[i], i))
        prediction = (
            sum(bool(train[i][1]["Label"][0]) for i in top) > len(top) / 2 if top else majority
        )
        retrieval_seconds.append(time.perf_counter() - tick)
        predictions.append(
            {
                "id": identifier(text),
                "exact_train_overlap": identifier(text) in train_ids,
                "prediction": prediction,
                "gold": bool(gold_record["Label"][0]),
                "neighbors": [{"id": identifier(train[i][0]), "score": scores[i]} for i in top],
            }
        )
    metrics = evaluate(predictions)
    clean = [r for r in predictions if not r["exact_train_overlap"]]
    majority_metrics = evaluate([{**r, "prediction": majority} for r in predictions])
    report = {
        "method": "B0-claim-bm25-knn-v1",
        "script_sha256": file_hash(Path(__file__)),
        "python": platform.python_version(),
        "split": args.split,
        "selection": "first N by SHA256(UTF-8 claim); no filtering by label/types",
        "train_n": len(train),
        "exact_overlap": overlap,
        "parameters": {"k1": 1.5, "b": 0.75, "neighbors": 5, "voting": "unweighted"},
        "hashes": {train_path.name: file_hash(train_path), eval_path.name: file_hash(eval_path)},
        "metrics": metrics,
        "nonoverlap_metrics": evaluate(clean) if clean else None,
        "majority_metrics": majority_metrics,
        "mean_retrieval_seconds": sum(retrieval_seconds) / len(retrieval_seconds),
        "elapsed_seconds": time.perf_counter() - started,
        "predictions": predictions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "predictions"}, indent=2))


if __name__ == "__main__":
    main()
