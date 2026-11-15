import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_h9_edge_path as h9  # noqa: E402
from factkg_h7_soft_matching import directed_arcs, indices  # noqa: E402


def triple(source, relation, target):
    return {"source": source, "relation": relation, "target": target}


def graph():
    return {
        "nodes": [{"id": "s", "label": "Film"}, {"id": "t", "label": "City"}],
        "edges": [{"source": "s", "relation": "producer is from", "target": "t"}],
    }


def test_candidate_paths_include_directed_two_hop_path():
    arcs = directed_arcs(
        [
            triple("Film", "producer", "Person"),
            triple("Person", "birthPlace", "City"),
            triple("Other", "birthPlace", "City"),
        ]
    )
    outgoing, _, by_pair = indices(arcs)
    paths = h9.candidate_paths("Film", "City", outgoing, by_pair)

    assert len(paths) == 1
    assert [arc["relation"] for arc in paths[0]] == ["producer", "birthPlace"]


def test_candidate_paths_reject_same_fact_walked_forward_and_backward():
    arcs = directed_arcs([triple("Film", "producer", "Person")])
    outgoing, _, by_pair = indices(arcs)

    assert h9.candidate_paths("Film", "Film", outgoing, by_pair) == []


def test_length_penalty_keeps_direct_edge_when_path_gain_is_too_small():
    arcs = directed_arcs(
        [
            triple("Film", "location", "City"),
            triple("Film", "producer", "Person"),
            triple("Person", "birthPlace", "City"),
        ]
    )
    outgoing, _, by_pair = indices(arcs)
    paths = h9.candidate_paths("Film", "City", outgoing, by_pair)

    def similarity(_query, candidate):
        return 0.75 if candidate.startswith("first edge") else 0.7

    best, score = h9.best_alignment("query", paths, similarity)
    assert len(best) == 1
    assert score == 0.7


def test_soft_search_and_evidence_can_select_two_hop_alignment():
    originals = [
        triple("Film", "unrelated", "City"),
        triple("Film", "producer", "Person"),
        triple("Person", "birthPlace", "City"),
    ]
    arcs = directed_arcs(originals)
    path_index = h9.build_path_index(arcs, {("Film", "City")})

    def similarity(_query, candidate):
        return 0.95 if candidate.startswith("first edge") else 0.1

    matches = h9.soft_search(graph(), {"s": ["Film"], "t": ["City"]}, path_index, similarity)
    evidence, alignments = h9.mapping_evidence(
        graph(), matches[0]["mapping"], path_index, similarity
    )

    assert evidence == originals[1:]
    assert alignments[0]["kg_path_length"] == 2
    assert alignments[0]["adjusted_similarity"] == 0.85


def test_soft_search_applies_explicit_candidate_provenance_penalty():
    arcs = directed_arcs(
        [
            triple("Film", "location", "City"),
            triple("Film", "location", "ExpandedCity"),
        ]
    )
    path_index = h9.build_path_index(arcs, {("Film", "City"), ("Film", "ExpandedCity")})

    def similarity(_query, candidate):
        return 0.9 if "ExpandedCity" in candidate else 0.8

    mapping = {"s": "Film", "t": "ExpandedCity"}
    unpenalized, _, _ = h9.mapping_cost(graph(), mapping, path_index, similarity, partial=False)
    penalized, _, _ = h9.mapping_cost(
        graph(),
        mapping,
        path_index,
        similarity,
        partial=False,
        node_penalties={("t", "ExpandedCity"): 1.0},
    )

    assert penalized - unpenalized == h9.NODE_WEIGHT / 2


def test_exact_paired_pvalue_is_two_sided():
    assert h9.exact_paired_pvalue(14, 0) == 0.0001220703125
    assert h9.exact_paired_pvalue(2, 2) == 1.0
