import json

from factkg_retry_invalid_extraction import extraction_prompt, needs_retry, repaired_row


def source_row(valid_views: int = 0) -> dict:
    return {
        "id": "claim-id",
        "text": "Alice wrote Book.",
        "graph": {"nodes": [], "edges": []},
        "valid_views": valid_views,
        "raw_views": ["old"],
        "usage": [{"tokens": {"finish_reason": "length"}, "seconds": 1.0}],
    }


def test_retry_selection_uses_validation_status() -> None:
    assert needs_retry(source_row(0))
    assert not needs_retry(source_row(1))


def test_prompt_keeps_exact_quote_constraint() -> None:
    system, user = extraction_prompt("Alice wrote Book.", "Extract facts.")
    assert "exact substring" in system
    assert "Alice wrote Book." in user


def test_repaired_row_uses_same_strict_parser() -> None:
    raw = json.dumps(
        {
            "nodes": [
                {"id": "n1", "label": "Alice"},
                {"id": "n2", "label": "Book"},
            ],
            "edges": [
                {
                    "source": "n1",
                    "relation": "wrote",
                    "target": "n2",
                    "polarity": "positive",
                    "quote": "Alice wrote Book",
                }
            ],
        }
    )
    row = repaired_row(source_row(), raw, {"total_tokens": 80}, 2.0, 512)
    assert row["valid_views"] == 1
    assert len(row["graph"]["edges"]) == 1
    assert row["retry"]["source_finish_reason"] == "length"
    assert row["retry"]["error"] is None


def test_repaired_row_fails_closed_on_ungrounded_quote() -> None:
    raw = json.dumps(
        {
            "nodes": [
                {"id": "n1", "label": "Alice"},
                {"id": "n2", "label": "Book"},
            ],
            "edges": [
                {
                    "source": "n1",
                    "relation": "wrote",
                    "target": "n2",
                    "polarity": "positive",
                    "quote": "Alice authored Book",
                }
            ],
        }
    )
    row = repaired_row(source_row(), raw, {"total_tokens": 80}, 2.0, 512)
    assert row["valid_views"] == 0
    assert row["graph"] == {"nodes": [], "edges": []}
    assert "exact substring" in row["retry"]["error"]
