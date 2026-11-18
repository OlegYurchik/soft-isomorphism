import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from factkg_h11_lazy_retrieval import compare_reference
from factkg_h11_unknown_fallback import (
    b1_rows,
    hybrid_verdict,
    is_correct,
    parse_verdict,
    seed_cache,
)


def test_hybrid_replaces_only_unknown_b1_verdict() -> None:
    assert hybrid_verdict("TRUE", "FALSE") == "TRUE"
    assert hybrid_verdict("FALSE", "TRUE") == "FALSE"
    assert hybrid_verdict("UNKNOWN", "TRUE") == "TRUE"


def test_parse_verdict_fails_closed_to_unknown() -> None:
    assert parse_verdict('{"verdict":"FALSE"}') == "FALSE"
    assert parse_verdict('{"verdict":"MAYBE"}') == "UNKNOWN"
    assert parse_verdict("not json") == "UNKNOWN"


def test_is_correct_treats_unknown_as_error() -> None:
    assert is_correct("TRUE", True)
    assert is_correct("FALSE", False)
    assert not is_correct("UNKNOWN", True)


def test_b1_rows_do_not_require_graph_retrieval(tmp_path) -> None:
    source = tmp_path / "candidates.jsonl"
    source.write_text(
        json.dumps({"id": "x", "text": "claim", "b1_evidence": [{"relation": "r"}]}) + "\n"
    )
    assert b1_rows(source) == [
        {
            "id": "x",
            "text": "claim",
            "arms": {"B1": {"evidence": [{"relation": "r"}]}},
        }
    ]


def test_seed_cache_reuses_existing_reader_response() -> None:
    assert seed_cache(
        {
            "x": {
                "evidence_sha256": "abc",
                "verdict": "TRUE",
                "usage": {"total_tokens": 4},
                "reader_seconds": 0.5,
            }
        }
    ) == {("x", "abc"): ("TRUE", {"total_tokens": 4}, 0.5)}


def test_reference_comparison_requires_exact_rows(tmp_path) -> None:
    reference = tmp_path / "reference.jsonl"
    reference.write_text(json.dumps({"id": "x", "cost": 0.25}) + "\n")
    assert compare_reference("H10", [{"id": "x", "cost": 0.25}], reference) == {
        "rows": 1,
        "exact_matches": 1,
        "missing": [],
        "mismatches": [],
    }
