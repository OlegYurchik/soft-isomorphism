import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_flat_2hop_control as flat  # noqa: E402
from factkg_h10_ablation_reader import paired_summary  # noqa: E402


def triple(source, relation, target):
    return {"source": source, "relation": relation, "target": target}


def similarity(_claim, candidate):
    if "useful" in candidate:
        return 0.9
    if "secondary" in candidate:
        return 0.7
    return 0.1


def test_flat_control_ranks_independent_real_triples_with_exact_budget():
    pool = [
        triple("A", "irrelevant", "B"),
        triple("A", "secondary", "C"),
        triple("D", "useful", "E"),
    ]

    evidence, selected = flat.rank_flat_evidence("claim", pool, 2, similarity)

    assert evidence == [pool[2], pool[1]]
    assert [item["similarity"] for item in selected] == [0.9, 0.7]
    assert all(item in pool for item in evidence)


def test_flat_control_deduplicates_and_breaks_ties_deterministically():
    first = triple("B", "same", "C")
    second = triple("A", "same", "C")
    evidence, _ = flat.rank_flat_evidence("claim", [first, second, first], 3, lambda *_: 0.5)

    assert evidence == [second, first]


def test_flat_control_rejects_negative_budget():
    with pytest.raises(ValueError, match="non-negative"):
        flat.rank_flat_evidence("claim", [], -1, similarity)


class FakeEncoder:
    def encode_many(self, _texts):
        return None

    def similarity(self, left, right):
        return similarity(left, right)


def test_score_row_contains_no_graph_mapping_or_beam_artifacts():
    row = {
        "id": "example",
        "text": "claim",
        "graph": {"nodes": [], "edges": []},
        "candidate_ids": {"n0": ["A"]},
        "pool_triples": [triple("A", "useful", "B"), triple("B", "secondary", "C")],
    }

    result = flat.score_row(row, 1, FakeEncoder())

    assert result["match"]["evidence"] == [row["pool_triples"][0]]
    assert set(result["match"]) == {"evidence", "selected"}
    assert "mapping" not in result["match"]
    assert "proposals" not in result
    assert result["evidence_budget"] == 1
    assert result["retrieval_wall_seconds"] >= 0
    assert result["retrieval_cpu_seconds"] >= 0


def test_input_digest_changes_with_pool_or_budget():
    row = {"text": "claim", "pool_triples": [triple("A", "r", "B")]}

    original = flat.input_digest(row, 1)

    assert flat.input_digest(row, 2) != original
    assert flat.input_digest({**row, "pool_triples": [triple("A", "s", "B")]}, 1) != original


def test_paired_summary_reports_direction_and_exact_test():
    records = [
        {"arms": {"H10": {"correct": True}, "flat": {"correct": False}}},
        {"arms": {"H10": {"correct": True}, "flat": {"correct": True}}},
        {"arms": {"H10": {"correct": False}, "flat": {"correct": True}}},
        {"arms": {"H10": {"correct": True}, "flat": {"correct": False}}},
    ]

    result = paired_summary(records, "H10", "flat")

    assert result["H10_only_correct"] == 2
    assert result["flat_only_correct"] == 1
    assert result["net_correct"] == 1
    assert 0 <= result["exact_two_sided_p"] <= 1
