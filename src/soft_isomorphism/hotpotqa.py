"""HotpotQA loading, sentence retrieval, and official-style metrics."""

from __future__ import annotations

import json
import math
import re
import string
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Sentence:
    title: str
    sent_id: int
    text: str


@dataclass(frozen=True)
class HotpotInput:
    id: str
    question: str
    sentences: tuple[Sentence, ...]


@dataclass(frozen=True)
class HotpotGold:
    id: str
    answer: str
    supporting_facts: frozenset[tuple[str, int]]


def _validate_row(row: dict) -> tuple[HotpotInput, HotpotGold]:
    identifier = row.get("id")
    question = row.get("question")
    answer = row.get("answer")
    context = row.get("context")
    supporting = row.get("supporting_facts")
    if not all(isinstance(value, str) for value in (identifier, question, answer)):
        raise ValueError("id, question, and answer must be strings")
    if not isinstance(context, dict) or not isinstance(supporting, dict):
        raise ValueError("context and supporting_facts must be structs")
    titles, paragraphs = context.get("title"), context.get("sentences")
    if not isinstance(titles, list) or not isinstance(paragraphs, list):
        raise ValueError("context title and sentences must be lists")
    if len(titles) != len(paragraphs):
        raise ValueError("context titles and paragraphs have different lengths")
    sentences = []
    for title, paragraph in zip(titles, paragraphs, strict=True):
        if not isinstance(title, str) or not isinstance(paragraph, list):
            raise ValueError("invalid context paragraph")
        for sent_id, text in enumerate(paragraph):
            if not isinstance(text, str):
                raise ValueError("sentence must be a string")
            sentences.append(Sentence(title, sent_id, text))
    gold_titles, gold_ids = supporting.get("title"), supporting.get("sent_id")
    if not isinstance(gold_titles, list) or not isinstance(gold_ids, list):
        raise ValueError("supporting fact fields must be lists")
    if len(gold_titles) != len(gold_ids):
        raise ValueError("supporting fact fields have different lengths")
    facts = frozenset()
    try:
        facts = frozenset(
            (title, int(sent_id))
            for title, sent_id in zip(gold_titles, gold_ids, strict=True)
            if isinstance(title, str)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid supporting fact") from exc
    available = {(sentence.title, sentence.sent_id) for sentence in sentences}
    if not facts <= available:
        raise ValueError("supporting fact is absent from contexts")
    return (
        HotpotInput(identifier, question, tuple(sentences)),
        HotpotGold(identifier, answer, facts),
    )


def load_hotpot_split(
    parquet_path: Path,
    split_path: Path,
    split: str,
    limit: int | None = None,
) -> tuple[list[HotpotInput], dict[str, HotpotGold]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised by installation, not unit tests
        raise RuntimeError(
            "install the hotpot optional dependency: uv sync --extra hotpot"
        ) from exc
    selected = json.loads(split_path.read_text()).get(split)
    if not isinstance(selected, list) or not all(isinstance(value, str) for value in selected):
        raise ValueError(f"split {split!r} is missing or invalid")
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        selected = selected[:limit]
    if len(selected) != len(set(selected)):
        raise ValueError("split contains duplicate ids")
    wanted = set(selected)
    table = pq.read_table(parquet_path)
    indexed = {row["id"]: row for row in table.to_pylist() if row.get("id") in wanted}
    missing = wanted - indexed.keys()
    if missing:
        raise ValueError(f"parquet is missing {len(missing)} selected ids")
    inputs, gold = [], {}
    for identifier in selected:
        method_input, evaluation = _validate_row(indexed[identifier])
        inputs.append(method_input)
        gold[identifier] = evaluation
    return inputs, gold


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def bm25_sentences(example: HotpotInput, limit: int = 5) -> list[tuple[Sentence, float]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    query = Counter(tokens(example.question))
    documents = [Counter(tokens(sentence.text)) for sentence in example.sentences]
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / len(lengths) if lengths else 1.0
    frequencies = Counter(term for document in documents for term in document)

    def score(index: int) -> float:
        total = 0.0
        for term, qtf in query.items():
            tf = documents[index][term]
            if not tf:
                continue
            df = frequencies[term]
            idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            total += qtf * idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * lengths[index] / average))
        return total

    ranked = sorted(
        ((sentence, score(index)) for index, sentence in enumerate(example.sentences)),
        key=lambda item: (-item[1], item[0].title, item[0].sent_id),
    )
    return ranked[:limit]


def normalize_answer(text: str) -> str:
    value = text.lower()
    value = "".join(character for character in value if character not in string.punctuation)
    value = re.sub(r"\b(a|an|the)\b", " ", value)
    return " ".join(value.split())


def answer_metrics(prediction: str, gold: str) -> dict[str, float]:
    normalized_prediction = normalize_answer(prediction)
    normalized_gold = normalize_answer(gold)
    exact = float(normalized_prediction == normalized_gold)
    prediction_tokens, gold_tokens = normalized_prediction.split(), normalized_gold.split()
    common = Counter(prediction_tokens) & Counter(gold_tokens)
    overlap = sum(common.values())
    if not prediction_tokens or not gold_tokens:
        f1 = float(prediction_tokens == gold_tokens)
    elif not overlap:
        f1 = 0.0
    else:
        precision = overlap / len(prediction_tokens)
        recall = overlap / len(gold_tokens)
        f1 = 2 * precision * recall / (precision + recall)
    return {"answer_em": exact, "answer_f1": f1}


def supporting_metrics(
    predicted: set[tuple[str, int]], gold: frozenset[tuple[str, int]]
) -> dict[str, float]:
    overlap = len(predicted & gold)
    precision = overlap / len(predicted) if predicted else float(not gold)
    recall = overlap / len(gold) if gold else float(not predicted)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "support_em": float(predicted == gold),
        "support_precision": precision,
        "support_recall": recall,
        "support_f1": f1,
    }
