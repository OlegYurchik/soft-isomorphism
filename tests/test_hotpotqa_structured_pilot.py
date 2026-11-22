import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_structured_pilot import (  # noqa: E402
    candidate_domains,
    evidence_from_match,
    shortlisted_titles,
)

from soft_isomorphism.hotpotqa import HotpotInput, Sentence  # noqa: E402


def test_candidate_domains_leave_unknown_for_path_proposal() -> None:
    graph = {
        "nodes": [{"id": "a", "label": "alice"}, {"id": "x", "label": "?"}],
        "edges": [],
    }
    triples = [{"source": "alice", "relation": "wrote", "target": "book"}]
    assert candidate_domains(graph, triples) == {"a": ["alice", "book"], "x": []}
    assert candidate_domains(graph, triples, freeze_exact=True) == {"a": ["alice"], "x": []}


def test_graph_evidence_is_first_and_bm25_fills_budget() -> None:
    example = HotpotInput(
        "id",
        "Who wrote Book?",
        (
            Sentence("Book", 0, "Alice wrote Book."),
            Sentence("Other", 0, "Irrelevant sentence."),
        ),
    )
    evidence, graph_count = evidence_from_match(example, [{"title": "Other", "sent_id": 0}], 2)
    assert graph_count == 1
    assert [(row["title"], row["sent_id"]) for row in evidence] == [
        ("Other", 0),
        ("Book", 0),
    ]


def test_paragraph_shortlist_uses_best_sentence_rank() -> None:
    example = HotpotInput(
        "id",
        "Who wrote Book?",
        (
            Sentence("Relevant", 0, "Alice wrote Book."),
            Sentence("Other", 0, "Irrelevant sentence."),
            Sentence("Relevant", 1, "Another sentence."),
        ),
    )
    assert shortlisted_titles(example, 1) == {"Relevant"}


def test_anchor_first_prioritizes_exact_query_entity_title() -> None:
    example = HotpotInput(
        "id",
        "What happened to WrestleMania IX?",
        (
            Sentence("Distractor", 0, "WrestleMania happened."),
            Sentence("WrestleMania IX", 0, "The event was held outdoors."),
        ),
    )
    graph = {"nodes": [{"id": "n0", "label": "wrestlemania ix"}], "edges": []}
    assert shortlisted_titles(example, 1, graph, anchor_first=True) == {"WrestleMania IX"}
