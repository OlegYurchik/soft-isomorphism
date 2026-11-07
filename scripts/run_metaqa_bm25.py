"""Run the text-only BM25 baseline on a MetaQA split.

Example:
    uv run python scripts/run_metaqa_bm25.py --data-dir data/MetaQA --hop 1 --split test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from soft_isomorphism.baselines.bm25 import (  # noqa: E402
    BM25Index,
    Fact,
    QAExample,
    evaluate_answers,
    rank_answers,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_facts(path: Path) -> list[Fact]:
    facts: list[Fact] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.rstrip("\n").split("|")
            if len(fields) != 3 or not all(field.strip() for field in fields):
                raise ValueError(f"Malformed KB triple at {path}:{line_number}")
            facts.append(Fact(*(field.strip() for field in fields)))
    if not facts:
        raise ValueError(f"No knowledge-base triples found in {path}")
    return facts


def load_examples(path: Path, *, hop: int, split: str) -> list[QAExample]:
    examples: list[QAExample] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 2:
                raise ValueError(f"Malformed QA row at {path}:{line_number}")
            question, raw_answers = fields
            answers = frozenset(answer.strip() for answer in raw_answers.split("|") if answer.strip())
            if not question.strip() or not answers:
                raise ValueError(f"Empty question/answers at {path}:{line_number}")
            examples.append(
                QAExample(
                    example_id=f"metaqa-{hop}hop-{split}-{line_number - 1}",
                    question=question.strip(),
                    answers=answers,
                )
            )
    if not examples:
        raise ValueError(f"No QA examples found in {path}")
    return examples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True, help="Root of official MetaQA data")
    parser.add_argument("--hop", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--split", choices=("train", "dev", "test"), default="test")
    parser.add_argument("--fact-limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    kb_path = args.data_dir / "kb.txt"
    qa_path = args.data_dir / f"{args.hop}-hop" / "vanilla" / f"qa_{args.split}.txt"
    facts = load_facts(kb_path)
    examples = load_examples(qa_path, hop=args.hop, split=args.split)

    log.info("Loaded %d KB triples and %d questions", len(facts), len(examples))
    index = BM25Index(fact.text for fact in facts)
    predictions: list[list[tuple[str, float]]] = []
    outputs: list[dict] = []

    for example in examples:
        ranked, evidence = rank_answers(
            example.question, facts, index, fact_limit=args.fact_limit
        )
        predictions.append(ranked)
        outputs.append(
            {
                "id": example.example_id,
                "question": example.question,
                "gold_answers": sorted(example.answers),
                "predicted_answers": [entity for entity, _ in ranked[:10]],
                "evidence_fact_indices": evidence[:20],
            }
        )

    metrics = evaluate_answers(examples, predictions)
    result = {
        "method": "BM25 over serialized KG triples; answer score is discounted sum of fact scores",
        "dataset": "MetaQA",
        "dataset_path": str(args.data_dir),
        "split": args.split,
        "hop": args.hop,
        "fact_limit": args.fact_limit,
        "metrics": metrics,
        "predictions": outputs,
    }
    output_path = args.output or REPO_ROOT / "results" / "MetaQA" / f"bm25_{args.hop}hop_{args.split}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Metrics: %s", metrics)
    log.info("Wrote %s", output_path)


if __name__ == "__main__":
    main()
