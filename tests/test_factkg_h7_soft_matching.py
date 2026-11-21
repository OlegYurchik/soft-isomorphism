import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_h7_soft_matching as h7  # noqa: E402


def triple(source, relation, target):
    return {"source": source, "relation": relation, "target": target}


def graph():
    return {
        "nodes": [{"id": "s", "label": "Ship"}, {"id": "t", "label": "City"}],
        "edges": [{"source": "s", "relation": "built in", "target": "t"}],
    }


def test_directed_arcs_keep_reverse_direction_explicit():
    original = triple("Ship", "builder", "Yard")
    arcs = h7.directed_arcs([original])
    assert arcs[0]["source"] == "Ship"
    assert arcs[1]["source"] == "Yard"
    assert arcs[1]["relation"] == "~builder"
    assert arcs[1]["evidence"] == original


def test_relation_guided_expansion_adds_neighbor_to_target_domain():
    arcs = h7.directed_arcs([triple("Ship", "locationCity", "Helsinki")])

    def similarity(_query, candidate):
        return 1.0 if "location city" in candidate else 0.0

    expanded = h7.expand_domains(graph(), {"s": ["Ship"], "t": ["City"]}, arcs, similarity)
    assert "Helsinki" in expanded["t"]


def test_soft_search_prefers_contextually_matching_connected_mapping():
    arcs = h7.directed_arcs(
        [
            triple("Ship", "unrelated", "City"),
            triple("Ship", "locationCity", "Helsinki"),
        ]
    )

    def similarity(_query, candidate):
        return 0.9 if "location city" in candidate else 0.1

    matches = h7.soft_search(graph(), {"s": ["Ship"], "t": ["City", "Helsinki"]}, arcs, similarity)
    assert matches[0]["mapping"] == {"s": "Ship", "t": "Helsinki"}


def test_mapping_evidence_returns_real_triple_for_reverse_match():
    original = triple("Yard", "builder", "Ship")
    reverse_graph = {
        "nodes": [{"id": "s", "label": "Ship"}, {"id": "t", "label": "Yard"}],
        "edges": [{"source": "s", "relation": "built by", "target": "t"}],
    }
    evidence = h7.mapping_evidence(
        reverse_graph,
        {"s": "Ship", "t": "Yard"},
        h7.directed_arcs([original]),
        lambda _query, _candidate: 1.0,
    )
    assert evidence == [original]
