from soft_isomorphism.matching import Edge, Node, Triple
from soft_isomorphism.search import beam_search, exhaustive_search


def sample():
    query = [Node("a", "Alice"), Node("b", "Book")]
    kg_nodes = {"A": Node("A", "Alice"), "B": Node("B", "Book"), "C": Node("C", "Carol")}
    kg_edges = [Triple("A", "author", "B"), Triple("C", "author", "B")]
    candidates = {"a": ["A", "C"], "b": ["B"]}
    return query, [Edge("a", "author", "b")], kg_nodes, kg_edges, candidates


def test_beam_matches_exhaustive_on_small_graph():
    args = sample()
    exact = exhaustive_search(*args)
    beam = beam_search(*args)
    assert exact.matches[0].mapping == {"a": "A", "b": "B"}
    assert beam.matches[0].mapping == exact.matches[0].mapping
    assert beam.matches[0].total_cost == 0
    assert beam.optimal_within_candidates


def test_beam_never_claims_optimum_after_pruning():
    outcome = beam_search(*sample(), beam_width=1)
    assert outcome.matches
    assert not outcome.optimal_within_candidates


def test_budget_exhaustion_is_visible():
    outcome = beam_search(*sample(), max_expansions=1)
    assert outcome.stop_reason == "budget_exhausted"
    assert not outcome.matches


def test_direction_matters_for_search():
    query, edges, kg_nodes, _, candidates = sample()
    reverse = [Triple("B", "author", "A")]
    result = exhaustive_search(query, edges, kg_nodes, reverse, candidates)
    assert result.matches[0].total_cost > 0
