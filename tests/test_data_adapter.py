"""Tests for the data adapter using synthetic fixtures.

These tests do not require the real datasets to be downloaded.
They verify schema correctness, ID tracing, direction preservation,
deduplication safety, and error handling.
"""

from pathlib import Path

import pytest

from soft_isomorphism.data.adapter import _parse_factkg_graph, _parse_gtsqa_graph
from soft_isomorphism.data.schema import Edge, Example, Source, Split

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_edge_frozen():
    e = Edge(head_id="Q1", rel_id="P31", tail_id="Q2")
    with pytest.raises(Exception):
        e.head_id = "Q999"  # type: ignore[misc]


def test_edge_to_triple():
    e = Edge("Q1", "P31", "Q2")
    assert e.to_triple() == ("Q1", "P31", "Q2")


def test_example_rejects_empty_id():
    with pytest.raises(ValueError, match="id must be non-empty"):
        Example(
            id="",
            source=Source.GTSQA,
            split=Split.TEST,
            text="q",
            gold_edges=[Edge("Q1", "P1", "Q2")],
        )


def test_example_rejects_empty_text():
    with pytest.raises(ValueError, match="text must be non-empty"):
        Example(
            id="x",
            source=Source.GTSQA,
            split=Split.TEST,
            text="",
            gold_edges=[Edge("Q1", "P1", "Q2")],
        )


def test_example_rejects_empty_gold_edges():
    with pytest.raises(ValueError, match="gold_edges is empty"):
        Example(id="x", source=Source.GTSQA, split=Split.TEST, text="q", gold_edges=[])


def test_example_rejects_edge_with_empty_rel():
    with pytest.raises(ValueError, match="empty head/rel/tail"):
        Example(
            id="x",
            source=Source.GTSQA,
            split=Split.TEST,
            text="q",
            gold_edges=[Edge("Q1", "", "Q2")],
        )


# ---------------------------------------------------------------------------
# GTSQA graph parser
# ---------------------------------------------------------------------------


def test_parse_gtsqa_list_of_triples():
    graph = [["Q142", "P36", "Q90"], ["Q90", "P17", "Q142"]]
    edges = _parse_gtsqa_graph(graph, "ex-1")
    assert len(edges) == 2
    assert edges[0] == Edge(head_id="Q142", rel_id="P36", tail_id="Q90")


def test_parse_gtsqa_dict_format():
    graph = {"edges": [{"head": "Q17", "rel": "P38", "tail": "Q8146"}]}
    edges = _parse_gtsqa_graph(graph, "ex-2")
    assert edges[0].head_id == "Q17"
    assert edges[0].rel_id == "P38"
    assert edges[0].tail_id == "Q8146"


def test_parse_gtsqa_empty_list_raises():
    with pytest.raises(ValueError, match="empty list"):
        _parse_gtsqa_graph([], "ex-3")


def test_parse_gtsqa_none_raises():
    with pytest.raises(ValueError, match="None"):
        _parse_gtsqa_graph(None, "ex-4")


def test_parse_gtsqa_unknown_format_raises():
    with pytest.raises(ValueError, match="Unknown GTSQA graph format"):
        _parse_gtsqa_graph("not-a-graph", "ex-5")


def test_parse_gtsqa_ids_are_strings():
    # IDs should be coerced to str even if source provides integers
    graph = [[123, 456, 789]]
    edges = _parse_gtsqa_graph(graph, "ex-6")
    assert edges[0].head_id == "123"
    assert edges[0].rel_id == "456"
    assert edges[0].tail_id == "789"


# ---------------------------------------------------------------------------
# FactKG graph parser
# ---------------------------------------------------------------------------


def test_parse_factkg_one_hop():
    graph = {"Murda_Beatz": [["occupation", "record_producer"]]}
    edges = _parse_factkg_graph(graph, "fk-1")
    assert len(edges) == 1
    assert edges[0] == Edge(head_id="Murda_Beatz", rel_id="occupation", tail_id="record_producer")


def test_parse_factkg_multi_hop():
    graph = {
        "Barack_Obama": [["place_of_birth", "Hawaii"]],
        "Hawaii": [["country", "United_States"]],
    }
    edges = _parse_factkg_graph(graph, "fk-2")
    assert len(edges) == 2
    heads = {e.head_id for e in edges}
    assert heads == {"Barack_Obama", "Hawaii"}


def test_parse_factkg_empty_dict_raises():
    with pytest.raises(ValueError, match="empty"):
        _parse_factkg_graph({}, "fk-3")


def test_parse_factkg_wrong_type_raises():
    with pytest.raises(ValueError, match="Expected dict"):
        _parse_factkg_graph([["a", "b", "c"]], "fk-4")


def test_parse_factkg_bad_adjacency_raises():
    with pytest.raises(ValueError, match="not a list"):
        _parse_factkg_graph({"entity": "not-a-list"}, "fk-5")


# ---------------------------------------------------------------------------
# load_factkg integration (uses fixture file)
# ---------------------------------------------------------------------------


def _make_factkg_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "factkg"
    json_dir = data_dir / "data"
    json_dir.mkdir(parents=True)
    src = FIXTURES / "factkg_sample.json"
    (json_dir / "factkg_dev.json").write_bytes(src.read_bytes())
    return data_dir


def test_load_factkg_dev(tmp_path):
    from soft_isomorphism.data.adapter import load_factkg

    data_dir = _make_factkg_dir(tmp_path)
    examples = load_factkg(data_dir, Split.DEV)
    assert len(examples) == 3
    for ex in examples:
        assert ex.source == Source.FACTKG
        assert ex.split == Split.DEV
        assert ex.text
        assert ex.gold_edges
        # gold_edges separated from metadata
        assert "graph" not in ex.metadata


def test_load_factkg_test_raises(tmp_path):
    from soft_isomorphism.data.adapter import load_factkg

    with pytest.raises(ValueError, match="no gold subgraph"):
        load_factkg(tmp_path, Split.TEST)


def test_load_factkg_missing_file_raises(tmp_path):
    from soft_isomorphism.data.adapter import load_factkg

    with pytest.raises(FileNotFoundError, match="factkg_dev.json"):
        load_factkg(tmp_path, Split.DEV)


def test_load_factkg_id_tracing(tmp_path):
    """Each example ID must be unique and traceable to the split."""
    from soft_isomorphism.data.adapter import load_factkg

    data_dir = _make_factkg_dir(tmp_path)
    examples = load_factkg(data_dir, Split.DEV)
    ids = [ex.id for ex in examples]
    assert len(ids) == len(set(ids)), "duplicate IDs"
    assert all("dev" in eid for eid in ids)


def test_load_factkg_metadata_label(tmp_path):
    from soft_isomorphism.data.adapter import load_factkg

    data_dir = _make_factkg_dir(tmp_path)
    examples = load_factkg(data_dir, Split.DEV)
    types = {ex.metadata["type"] for ex in examples}
    assert "One-hop" in types
    assert "Multi-hop" in types
