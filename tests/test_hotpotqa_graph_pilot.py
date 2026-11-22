import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_graph_pilot import (  # noqa: E402
    context_prompt,
    digest_paragraph,
    parse_context_graph,
    query_prompt,
    validate_query_graph,
)


def valid_raw() -> str:
    return json.dumps(
        {
            "nodes": [
                {"id": "n0", "label": "Alice"},
                {"id": "n1", "label": "Book"},
            ],
            "edges": [
                {
                    "source": "n0",
                    "relation": "wrote",
                    "target": "n1",
                    "polarity": "positive",
                    "sent_id": 0,
                    "quote": "Alice wrote Book",
                }
            ],
        }
    )


def test_context_parser_preserves_provenance() -> None:
    triples = parse_context_graph(valid_raw(), "Alice", ["Alice wrote Book."])
    assert triples == [
        {
            "source": "alice",
            "relation": "wrote",
            "target": "book",
            "polarity": "positive",
            "title": "Alice",
            "sent_id": 0,
            "quote": "Alice wrote Book",
        }
    ]


def test_context_parser_rejects_wrong_sentence_quote() -> None:
    data = json.loads(valid_raw())
    data["edges"][0]["quote"] = "Alice authored Book"
    with pytest.raises(ValueError, match="exact"):
        parse_context_graph(json.dumps(data), "Alice", ["Alice wrote Book."])


def test_context_parser_allows_title_as_implicit_subject() -> None:
    data = json.loads(valid_raw())
    data["nodes"][0]["label"] = "Article title"
    data["edges"][0]["quote"] = "It wrote Book"
    triples = parse_context_graph(json.dumps(data), "Article title", ["It wrote Book."])
    assert triples[0]["source"] == "article title"


def test_context_parser_resolves_unique_label_endpoints() -> None:
    data = json.loads(valid_raw())
    data["edges"][0]["source"] = "Alice"
    data["edges"][0]["target"] = "Book"
    triples = parse_context_graph(json.dumps(data), "Alice", ["Alice wrote Book."])
    assert triples[0]["source"] == "alice"


def test_paragraph_digest_is_deterministic_and_content_sensitive() -> None:
    assert digest_paragraph("A", ["B"]) == digest_paragraph("A", ["B"])
    assert digest_paragraph("A", ["B"]) != digest_paragraph("A", ["C"])


def test_prompts_require_unknown_and_provenance() -> None:
    query_system, _ = query_prompt("Who wrote Book?")
    context_system, context_user = context_prompt("Book", ["Alice wrote it."])
    assert "label '?'" in query_system
    assert "exact quote" in context_system
    assert "[0] Alice wrote it." in context_user


def test_query_graph_requires_one_incident_unknown() -> None:
    validate_query_graph(
        {
            "nodes": [{"id": "n0", "label": "?"}, {"id": "n1", "label": "book"}],
            "edges": [{"source": "n0", "target": "n1", "relation": "wrote"}],
        }
    )
    with pytest.raises(ValueError, match="exactly one"):
        validate_query_graph(
            {
                "nodes": [{"id": "n0", "label": "who"}],
                "edges": [{"source": "n0", "target": "n0", "relation": "wrote"}],
            }
        )
