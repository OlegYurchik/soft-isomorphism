"""Metric and input-semantics checks for the inexpensive verification control."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "factkg_baseline",
    Path(__file__).parents[1] / "scripts" / "run_factkg_baseline.py",
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def test_negation_survives_tokenization():
    assert "not" in baseline.tokens("Paris is not in Germany")
    assert "never" in baseline.tokens("This person never wrote a book")


def test_majority_classifier_is_not_perfect_macro_f1():
    rows = [{"prediction": False, "gold": False}] * 3
    rows += [{"prediction": False, "gold": True}]
    metrics = baseline.evaluate(rows)
    assert metrics["accuracy"] == 0.75
    assert metrics["macro_f1"] == pytest.approx(3 / 7)


def test_completely_wrong_predictions():
    metrics = baseline.evaluate(
        [{"prediction": True, "gold": False}, {"prediction": False, "gold": True}]
    )
    assert metrics["accuracy"] == metrics["macro_f1"] == 0


def test_empty_evaluation_is_an_error():
    with pytest.raises(ValueError, match="empty split"):
        baseline.evaluate([])
