"""Paired comparison of HotpotQA B1 and graph-aware runs."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from pathlib import Path

from soft_isomorphism.hotpotqa import (
    answer_metrics,
    load_hotpot_split,
    supporting_metrics,
)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def direction_counts(deltas: list[float]) -> dict[str, int]:
    return {
        "improved": sum(value > 0 for value in deltas),
        "regressed": sum(value < 0 for value in deltas),
        "tied": sum(value == 0 for value in deltas),
    }


def sign_flip_pvalue(deltas: list[float], simulations: int = 100_000) -> float:
    nonzero = [value for value in deltas if value]
    if not nonzero:
        return 1.0
    observed = abs(mean(deltas))
    if len(nonzero) <= 20:
        values = (
            abs(sum(sign * value for sign, value in zip(signs, nonzero, strict=True)) / len(deltas))
            for signs in itertools.product((-1, 1), repeat=len(nonzero))
        )
        total = 2 ** len(nonzero)
        return sum(value >= observed - 1e-15 for value in values) / total
    rng = random.Random(42)
    extreme = 0
    for _ in range(simulations):
        value = abs(sum(item if rng.getrandbits(1) else -item for item in nonzero) / len(deltas))
        extreme += value >= observed - 1e-15
    return (extreme + 1) / (simulations + 1)


def bootstrap_interval(deltas: list[float], samples: int = 10_000) -> list[float]:
    rng = random.Random(42)
    estimates = sorted(
        mean([deltas[rng.randrange(len(deltas))] for _ in deltas]) for _ in range(samples)
    )
    return [estimates[int(samples * 0.025)], estimates[int(samples * 0.975) - 1]]


def exact_binary_pvalue(wins: int, losses: int) -> float:
    total = wins + losses
    if not total:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(total, index) for index in range(tail + 1)) / 2**total)


def read_rows(path: Path) -> dict[str, dict]:
    return {row["id"]: row for row in map(json.loads, path.read_text().splitlines())}


def run(args: argparse.Namespace) -> None:
    inputs, gold = load_hotpot_split(
        args.parquet, args.split_file, "development", args.limit, args.offset
    )
    b1_predictions = read_rows(args.b1_dir / "bm25-predictions.jsonl")
    graph_predictions = read_rows(args.graph_dir / "structured-predictions.jsonl")
    b1_retrieval = read_rows(args.b1_dir / "bm25-retrieval.jsonl")
    graph_retrieval = read_rows(args.graph_dir / "structured-retrieval.jsonl")
    answer_deltas, em_deltas, support_deltas = [], [], []
    same_evidence = 0
    for example in inputs:
        identifier = example.id
        b1_answer = answer_metrics(b1_predictions[identifier]["answer"], gold[identifier].answer)
        graph_answer = answer_metrics(
            graph_predictions[identifier]["answer"], gold[identifier].answer
        )
        answer_deltas.append(graph_answer["answer_f1"] - b1_answer["answer_f1"])
        em_deltas.append(graph_answer["answer_em"] - b1_answer["answer_em"])
        b1_set = {(row["title"], row["sent_id"]) for row in b1_retrieval[identifier]["evidence"]}
        graph_set = {
            (row["title"], row["sent_id"]) for row in graph_retrieval[identifier]["evidence"]
        }
        b1_support = supporting_metrics(b1_set, gold[identifier].supporting_facts)
        graph_support = supporting_metrics(graph_set, gold[identifier].supporting_facts)
        support_deltas.append(graph_support["support_f1"] - b1_support["support_f1"])
        same_evidence += b1_set == graph_set
    em_counts = direction_counts(em_deltas)
    summary = {
        "claims": len(inputs),
        "offset": args.offset,
        "answer_f1": {
            "delta": mean(answer_deltas),
            **direction_counts(answer_deltas),
            "sign_flip_pvalue": sign_flip_pvalue(answer_deltas),
            "bootstrap_95": bootstrap_interval(answer_deltas),
        },
        "answer_em": {
            "delta": mean(em_deltas),
            **em_counts,
            "exact_pvalue": exact_binary_pvalue(em_counts["improved"], em_counts["regressed"]),
        },
        "support_f1": {
            "delta": mean(support_deltas),
            **direction_counts(support_deltas),
            "sign_flip_pvalue": sign_flip_pvalue(support_deltas),
        },
        "same_evidence": same_evidence,
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, default=Path("data/hotpotqa/validation.parquet"))
    parser.add_argument("--split-file", type=Path, default=Path("configs/splits/hotpotqa-e1.json"))
    parser.add_argument("--offset", type=int, default=20)
    parser.add_argument("--limit", type=int, default=180)
    parser.add_argument("--b1-dir", type=Path, required=True)
    parser.add_argument("--graph-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
