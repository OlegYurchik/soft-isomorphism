"""A dependency-free BM25 baseline over MetaQA knowledge-base triples."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, punctuation-insensitive English tokenization."""
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class Fact:
    subject: str
    relation: str
    object: str

    @property
    def text(self) -> str:
        return f"{self.subject} {self.relation.replace('_', ' ')} {self.object}"


class BM25Index:
    """Small in-memory Okapi BM25 index with deterministic tie-breaking."""

    def __init__(self, documents: Iterable[str], *, k1: float = 1.5, b: float = 0.75):
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be in [0, 1]")

        self.k1 = k1
        self.b = b
        self.tokens = [tokenize(document) for document in documents]
        self.lengths = [len(document) for document in self.tokens]
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.term_freqs = [Counter(document) for document in self.tokens]
        doc_freqs: Counter[str] = Counter()
        postings: defaultdict[str, list[tuple[int, int]]] = defaultdict(list)
        for doc_index, term_freq in enumerate(self.term_freqs):
            doc_freqs.update(term_freq.keys())
            for term, frequency in term_freq.items():
                postings[term].append((doc_index, frequency))
        self.postings = dict(postings)
        self.norms = [
            self.k1 * (1 - self.b + length / self.avgdl) if self.avgdl else 0.0
            for length in self.lengths
        ]
        self.idf = {
            term: math.log(1 + (len(self.tokens) - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in doc_freqs.items()
        }

    def search(self, query: str, *, limit: int = 1000) -> list[tuple[int, float]]:
        """Return (document index, score), descending by score then source order."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        query_terms = tokenize(query)
        if not self.tokens or not query_terms or self.avgdl == 0:
            return []

        query_counts = Counter(query_terms)
        scores: defaultdict[int, float] = defaultdict(float)
        for term, qtf in query_counts.items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            query_weight = min(qtf, 2)
            for index, tf in self.postings.get(term, []):
                norm = self.norms[index]
                scores[index] += idf * (tf * (self.k1 + 1) / (tf + norm)) * query_weight
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:limit]


@dataclass(frozen=True)
class QAExample:
    example_id: str
    question: str
    answers: frozenset[str]


def rank_answers(
    question: str,
    facts: list[Fact],
    index: BM25Index,
    *,
    fact_limit: int = 1000,
) -> tuple[list[tuple[str, float]], list[int]]:
    """Aggregate retrieved fact scores into entity candidates.

    Bracketed topic entities are supplied by MetaQA question format and excluded
    from answer candidates. No gold answer or relation path is used for retrieval.
    """
    topics = {topic.strip() for topic in re.findall(r"\[([^\]]+)\]", question)}
    entity_scores: defaultdict[str, float] = defaultdict(float)
    evidence: list[int] = []

    for rank, (fact_index, score) in enumerate(index.search(question, limit=fact_limit), start=1):
        evidence.append(fact_index)
        contribution = score / math.log2(rank + 1)
        fact = facts[fact_index]
        for entity in {fact.subject, fact.object}:
            if entity not in topics:
                entity_scores[entity] += contribution

    ranked = sorted(entity_scores.items(), key=lambda item: (-item[1], item[0]))
    return ranked, evidence


def evaluate_answers(
    examples: list[QAExample],
    predictions: list[list[tuple[str, float]]],
    *,
    ks: tuple[int, ...] = (1, 5, 10),
) -> dict[str, float | int]:
    if len(examples) != len(predictions):
        raise ValueError("examples and predictions must have equal length")
    if not examples:
        raise ValueError("cannot evaluate an empty split")
    if any(k <= 0 for k in ks):
        raise ValueError("all k values must be positive")

    hits = {k: 0 for k in ks}
    reciprocal_rank = 0.0
    no_prediction = 0

    for example, ranked in zip(examples, predictions, strict=True):
        ranked_entities = [entity for entity, _ in ranked]
        if not ranked_entities:
            no_prediction += 1
            continue
        first_rank = next(
            (rank for rank, entity in enumerate(ranked_entities, start=1) if entity in example.answers),
            None,
        )
        if first_rank is not None:
            reciprocal_rank += 1 / first_rank
            for k in ks:
                if first_rank <= k:
                    hits[k] += 1

    count = len(examples)
    result: dict[str, float | int] = {
        f"hits_at_{k}": hits[k] / count for k in ks
    }
    result["mrr"] = reciprocal_rank / count
    result["no_prediction"] = no_prediction
    result["num_examples"] = count
    return result
