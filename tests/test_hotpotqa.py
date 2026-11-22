import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_bm25_pilot import parse_answer  # noqa: E402

from soft_isomorphism.hotpotqa import (  # noqa: E402
    HotpotInput,
    Sentence,
    _validate_row,
    answer_metrics,
    bm25_sentences,
    normalize_answer,
    supporting_metrics,
)


def sample_row() -> dict:
    return {
        "id": "q1",
        "question": "Who wrote the book?",
        "answer": "Alice Smith",
        "context": {
            "title": ["Book", "Noise"],
            "sentences": [["Alice Smith wrote the book."], ["Unrelated sentence."]],
        },
        "supporting_facts": {"title": ["Book"], "sent_id": [0]},
    }


def test_validate_row_separates_method_input_from_gold() -> None:
    method_input, gold = _validate_row(sample_row())
    assert method_input.id == gold.id == "q1"
    assert not hasattr(method_input, "answer")
    assert gold.supporting_facts == frozenset({("Book", 0)})


def test_validate_row_rejects_missing_supporting_sentence() -> None:
    row = sample_row()
    row["supporting_facts"]["sent_id"] = [3]
    with pytest.raises(ValueError, match="absent"):
        _validate_row(row)


def test_bm25_prefers_question_terms_and_is_deterministic() -> None:
    example = HotpotInput(
        "q",
        "Who wrote the book?",
        (
            Sentence("Noise", 0, "The sky is blue."),
            Sentence("Book", 0, "Alice wrote the book."),
            Sentence("Another", 0, "A book was sold."),
        ),
    )
    ranked = bm25_sentences(example, 2)
    assert ranked[0][0] == Sentence("Book", 0, "Alice wrote the book.")
    assert len(ranked) == 2


def test_official_style_answer_normalization_and_f1() -> None:
    assert normalize_answer("The Alice, Smith!") == "alice smith"
    assert answer_metrics("Alice Smith", "the Alice Smith") == {"answer_em": 1.0, "answer_f1": 1.0}
    assert answer_metrics("Alice", "Alice Smith")["answer_f1"] == pytest.approx(2 / 3)


def test_supporting_metrics_use_title_and_sentence_id() -> None:
    result = supporting_metrics({("A", 0), ("B", 0)}, frozenset({("A", 0), ("C", 1)}))
    assert result["support_precision"] == 0.5
    assert result["support_recall"] == 0.5
    assert result["support_f1"] == 0.5
    assert result["support_em"] == 0.0


def test_reader_answer_parser_fails_closed() -> None:
    assert parse_answer(json.dumps({"answer": "  Alice  "})) == "Alice"
    assert parse_answer("not json") == ""
