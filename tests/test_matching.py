import pytest
from pytest import approx

from soft_isomorphism.matching import Edge, Node, Triple, score_mapping, validate_mapping


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
    nodes, edges, candidates, triples = graph()
    full = score_mapping(nodes, edges, candidates, triples, {"a": "A", "b": "B"})
    missing = score_mapping(nodes, edges, candidates, triples, {"a": "A", "b": None})
    assert missing > full


def test_injective_constraint():
    with pytest.raises(ValueError, match="injective"):
        validate_mapping({"a": "A", "b": "A"})
