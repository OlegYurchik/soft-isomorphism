import pytest
from pytest import approx

from soft_isomorphism.matching import (
    Edge,
    Node,
    Triple,
    score_mapping,
    score_mapping_breakdown,
    validate_mapping,
)


def graph():
    nodes = [Node("a", "Alice"), Node("b", "writer")]
    edges = [Edge("a", "author", "b")]
    candidates = {"A": Node("A", "Alice"), "B": Node("B", "writer")}
    triples = [Triple("A", "author", "B")]
    return nodes, edges, candidates, triples


def test_exact_mapping_has_zero_cost():
    nodes, edges, candidates, triples = graph()
    assert score_mapping(nodes, edges, candidates, triples, {"a": "A", "b": "B"}) == approx(0)


def test_confidence_downweights_unreliable_missing_edge():
    nodes, edges, candidates, triples = graph()
    noisy = Edge("a", "invented_relation", "b", confidence=0.2)
    unweighted = score_mapping(
        nodes, [*edges, Edge("a", noisy.relation, "b")], candidates, triples, {"a": "A", "b": "B"}
    )
    weighted = score_mapping(nodes, [*edges, noisy], candidates, triples, {"a": "A", "b": "B"})
    assert weighted < unweighted


def test_null_mapping_has_explicit_node_penalty():
    nodes = [Node(str(i), str(i)) for i in range(5)]
    candidates = {str(i): Node(str(i), str(i)) for i in range(5)}
    full = score_mapping(nodes, [], candidates, [], {str(i): str(i) for i in range(5)})
    missing = score_mapping(
        nodes, [], candidates, [], {**{str(i): str(i) for i in range(4)}, "4": None}
    )
    assert missing > full


def test_direction_and_relation_change_are_penalized():
    nodes, edges, candidates, triples = graph()
    mapping = {"a": "A", "b": "B"}
    assert score_mapping(nodes, edges, candidates, [Triple("B", "author", "A")], mapping) > 0
    assert score_mapping(nodes, edges, candidates, [Triple("A", "publisher", "B")], mapping) > 0
    assert score_mapping(nodes, edges, candidates, triples, mapping) == 0


def test_breakdown_and_coverage_validation():
    nodes, edges, candidates, triples = graph()
    mapping = {"a": "A", "b": "B"}
    breakdown = score_mapping_breakdown(nodes, edges, candidates, triples, mapping)
    assert breakdown.total == 0
    assert breakdown.matched_nodes == 2
    with pytest.raises(ValueError, match="80%"):
        score_mapping(nodes, edges, candidates, triples, {"a": "A", "b": None})
    with pytest.raises(ValueError, match="unknown candidate"):
        score_mapping(nodes, edges, candidates, triples, {"a": "A", "b": "Z"})


def test_injective_constraint():
    with pytest.raises(ValueError, match="injective"):
        validate_mapping({"a": "A", "b": "A"})
