import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_h5_experiment as h5  # noqa: E402


def triple(source, relation, target):
    return {"source": source, "relation": relation, "target": target}


def test_enumerate_paths_starts_from_linked_candidates_and_is_simple():
    row = {
        "text": "A reaches C through B",
        "candidate_ids": {"n0": ["A"]},
        "pool_triples": [triple("A", "first", "B"), triple("B", "second", "C")],
    }
    paths = h5.enumerate_paths(row)
    assert any(
        [(arc["source"], arc["target"]) for arc in path] == [("A", "B"), ("B", "C")]
        for path in paths
    )
    assert all(
        len({path[0]["source"], *(arc["target"] for arc in path)}) == len(path) + 1
        for path in paths
    )


def test_path_evidence_restores_original_triple_after_reverse_walk():
    original = triple("A", "r", "B")
    reverse = h5.build_arcs([original])["B"][0]
    assert reverse["relation"] == "~r"
    assert h5.path_evidence((reverse,)) == [original]


def test_merge_with_b1_adds_complete_unit_with_fixed_budget():
    b1 = [triple("A", f"r{i}", f"B{i}") for i in range(20)]
    path = [triple("X", "p1", "Y"), triple("Y", "p2", "Z")]
    result = h5.merge_with_b1(b1, [path])
    assert result[: h5.BASE_KEEP] == b1[: h5.BASE_KEEP]
    assert all(item in result for item in path)
    assert len(result) == h5.EVIDENCE_BUDGET


def test_merge_with_b1_falls_back_when_complete_unit_does_not_fit():
    b1 = [triple("A", f"r{i}", f"B{i}") for i in range(20)]
    oversized = [triple("X", f"p{i}", f"Y{i}") for i in range(9)]
    assert h5.merge_with_b1(b1, [oversized]) == b1
