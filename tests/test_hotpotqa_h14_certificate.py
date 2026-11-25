import sys
from pathlib import Path

from pytest import approx

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_h14_certificate import (  # noqa: E402
    certify_drop_one,
    distinct_evidence_margin,
    evidence_key,
    final_candidates,
)

from soft_isomorphism.hotpotqa import HotpotInput, Sentence  # noqa: E402


def test_evidence_key_ignores_graph_identity_and_deduplicates_sentences() -> None:
    evidence = [
        {"title": "B", "sent_id": 1, "source": "x", "target": "y"},
        {"title": "A", "sent_id": 0, "source": "u", "target": "v"},
        {"title": "B", "sent_id": 1, "source": "other", "target": "node"},
    ]
    assert evidence_key(evidence) == (("A", 0), ("B", 1))


def test_distinct_evidence_margin_uses_cost_gap() -> None:
    assert distinct_evidence_margin([{"cost": 0.2}, {"cost": 0.35}]) == approx(0.15)
    assert distinct_evidence_margin([{"cost": 0.2}]) is None


def test_certificate_returns_first_counterexample() -> None:
    base = (("A", 0),)
    worlds = [
        {"operation": "drop_triple", "triple_index": 0, "evidence_key": base},
        {"operation": "drop_triple", "triple_index": 1, "evidence_key": (("B", 0),)},
    ]
    certified, witness = certify_drop_one(base, worlds)
    assert not certified
    assert witness == worlds[1]


def test_certificate_accepts_only_when_all_worlds_preserve_evidence() -> None:
    base = (("A", 0),)
    worlds = [
        {"operation": "drop_triple", "triple_index": index, "evidence_key": base}
        for index in range(3)
    ]
    assert certify_drop_one(base, worlds) == (True, None)


def test_final_candidates_certify_actual_bm25_filled_output() -> None:
    example = HotpotInput(
        "id",
        "Who wrote Book?",
        (
            Sentence("Book", 0, "Alice wrote Book."),
            Sentence("Other", 0, "Other sentence."),
        ),
    )
    candidates = [
        {
            "cost": 0.1,
            "evidence": [{"title": "Book", "sent_id": 0}],
            "evidence_key": (("Book", 0),),
        },
        {
            "cost": 0.2,
            "evidence": [],
            "evidence_key": (),
        },
    ]
    final = final_candidates(example, candidates, evidence_budget=2)
    assert len(final) == 1
    assert final[0]["evidence_key"] == (("Book", 0), ("Other", 0))
