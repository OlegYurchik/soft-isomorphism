import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_h10_endpoint_paths as h10  # noqa: E402
from factkg_h7_soft_matching import directed_arcs, indices  # noqa: E402


def triple(source, relation, target):
    return {"source": source, "relation": relation, "target": target}


def graph():
    return {
        "nodes": [{"id": "s", "label": "Film"}, {"id": "t", "label": "City"}],
        "edges": [{"source": "s", "relation": "producer is from", "target": "t"}],
    }


class FakeEncoder:
    def encode_many(self, _texts):
        return None

    def similarity(self, _query, candidate):
        if "producer then birth place" in candidate:
            return 1.0
        if "birth place" in candidate:
            return 0.6
        return 0.1


def test_forward_and_backward_paths_preserve_direction():
    arcs = directed_arcs(
        [triple("Film", "producer", "Person"), triple("Person", "birthPlace", "City")]
    )
    outgoing, incoming, _ = indices(arcs)

    forward = list(h10.forward_paths("Film", outgoing))
    backward = list(h10.backward_paths("City", incoming))

    assert any([arc["relation"] for arc in path] == ["producer", "birthPlace"] for path in forward)
    assert any([arc["relation"] for arc in path] == ["producer", "birthPlace"] for path in backward)


def test_path_guided_proposal_recovers_missing_endpoint():
    arcs = directed_arcs(
        [triple("Film", "producer", "Person"), triple("Person", "birthPlace", "City")]
    )
    initial = {"s": ["Film"], "t": ["WrongCity"]}

    expanded, penalties, proposals = h10.propose_domains(graph(), initial, arcs, FakeEncoder())

    assert "City" in expanded["t"]
    assert penalties["t", "City"] == h10.EXPANDED_NODE_PENALTY
    assert any(
        record["candidate"] == "City" and len(record["path_evidence"]) == 2 for record in proposals
    )


def test_proposal_expansion_is_capped_per_query_node():
    arcs = directed_arcs(
        [
            triple("Film", "location", "CityA"),
            triple("Film", "location", "CityB"),
            triple("Film", "location", "CityC"),
        ]
    )
    initial = {"s": ["Film"], "t": ["WrongCity"]}

    expanded, penalties, proposals = h10.propose_domains(graph(), initial, arcs, FakeEncoder())

    assert len(expanded["t"]) == 1 + h10.NEW_CANDIDATES_PER_NODE
    assert len([record for record in proposals if record["node"] == "t"]) == 2
    assert len([key for key in penalties if key[0] == "t"]) == 2


def test_one_hop_ablation_excludes_two_hop_proposals():
    arcs = directed_arcs(
        [triple("Film", "producer", "Person"), triple("Person", "birthPlace", "City")]
    )
    _, _, proposals = h10.propose_domains(
        graph(), {"s": ["Film"], "t": []}, arcs, FakeEncoder(), max_path_length=1
    )
    assert all(len(item["path_evidence"]) == 1 for item in proposals)


def test_candidate_count_and_penalty_are_configurable():
    arcs = directed_arcs([triple("Film", "location", "CityA"), triple("Film", "location", "CityB")])
    expanded, penalties, _ = h10.propose_domains(
        graph(),
        {"s": ["Film"], "t": []},
        arcs,
        FakeEncoder(),
        candidates_per_node=1,
        expanded_node_penalty=0.0,
    )
    assert len(expanded["t"]) == 1
    assert set(penalties.values()) == {0.0}
