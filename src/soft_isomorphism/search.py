"""Bounded graph mapping search for the E1 protocol."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil
from time import perf_counter
from typing import Mapping, Sequence

from .matching import Edge, Node, Triple, _edge_distance, label_distance, score_mapping_breakdown


@dataclass(frozen=True)
class Match:
    mapping: dict[str, str | None]
    total_cost: float
    node_cost: float
    edge_cost: float


@dataclass(frozen=True)
class SearchOutcome:
    matches: tuple[Match, ...]
    expanded_states: int
    elapsed_seconds: float
    stop_reason: str
    optimal_within_candidates: bool


def _candidate_choices(
    node: Node, candidate_ids: Mapping[str, Sequence[str]], kg_nodes: Mapping[str, Node]
) -> list[str | None]:
    if node.id not in candidate_ids:
        raise ValueError(f"missing candidate list for query node {node.id}")
    choices = list(dict.fromkeys(candidate_ids[node.id]))
    if any(choice not in kg_nodes for choice in choices):
        raise ValueError(f"unknown KG candidate for query node {node.id}")
    return [*choices, None]


def _as_match(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    kg_nodes: Mapping[str, Node],
    kg_edges: Sequence[Triple],
    mapping: dict[str, str | None],
) -> Match:
    cost = score_mapping_breakdown(nodes, edges, kg_nodes, kg_edges, mapping)
    return Match(mapping.copy(), cost.total, cost.node, cost.edge)


def _match_key(match: Match) -> tuple[float, tuple[str, ...]]:
    return match.total_cost, tuple(
        "~" if v is None else v for _, v in sorted(match.mapping.items())
    )


def exhaustive_search(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    kg_nodes: Mapping[str, Node],
    kg_edges: Sequence[Triple],
    candidate_ids: Mapping[str, Sequence[str]],
    *,
    top_k: int = 10,
) -> SearchOutcome:
    """Exact oracle for small graphs only, with an explicit size guard."""
    if not nodes or len(nodes) > 5:
        raise ValueError("exhaustive search accepts 1..5 query nodes")
    choices = [_candidate_choices(node, candidate_ids, kg_nodes) for node in nodes]
    if any(len(row) > 4 for row in choices):
        raise ValueError("exhaustive search accepts at most three candidates per node")
    started = perf_counter()
    matches: list[Match] = []
    expanded = 0
    required = max(1, ceil(0.8 * len(nodes)))
    for assignment in product(*choices):
        expanded += 1
        nonnull = [value for value in assignment if value is not None]
        if len(nonnull) < required or len(nonnull) != len(set(nonnull)):
            continue
        matches.append(
            _as_match(
                nodes, edges, kg_nodes, kg_edges, dict(zip((n.id for n in nodes), assignment))
            )
        )
    matches.sort(key=_match_key)
    return SearchOutcome(
        tuple(matches[:top_k]), expanded, perf_counter() - started, "complete", True
    )


def _lower_bound(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    kg_nodes: Mapping[str, Node],
    by_pair: Mapping[tuple[str, str], Sequence[str]],
    partial: Mapping[str, str | None],
) -> float:
    node_sum = 0.0
    for node in nodes:
        if node.id in partial:
            image = partial[node.id]
            node_sum += (
                0.8
                if image is None
                else (
                    0.0 if node.label == "?" else label_distance(node.label, kg_nodes[image].label)
                )
            )
    if not edges:
        return node_sum / len(nodes)
    edge_sum = 0.0
    mass = sum(max(0.2, min(1.0, edge.confidence)) for edge in edges)
    for edge in edges:
        if edge.source not in partial or edge.target not in partial:
            continue
        source, target = partial[edge.source], partial[edge.target]
        best = 1.0
        if source is not None and target is not None:
            best = min(
                (_edge_distance(edge.relation, r) for r in by_pair.get((source, target), ())),
                default=1.0,
            )
        edge_sum += max(0.2, min(1.0, edge.confidence)) * best
    return 0.3 * node_sum / len(nodes) + 0.7 * edge_sum / mass


def beam_search(
    nodes: Sequence[Node],
    edges: Sequence[Edge],
    kg_nodes: Mapping[str, Node],
    kg_edges: Sequence[Triple],
    candidate_ids: Mapping[str, Sequence[str]],
    *,
    beam_width: int = 64,
    max_expansions: int = 50_000,
    top_k: int = 10,
) -> SearchOutcome:
    """Approximate beam search. Never claims global optimality after beam pruning."""
    if not nodes or beam_width < 1 or max_expansions < 1 or top_k < 1:
        raise ValueError("nonempty nodes and positive limits required")
    started = perf_counter()
    degree = {node.id: 0 for node in nodes}
    for edge in edges:
        if edge.source not in degree or edge.target not in degree:
            raise ValueError("query edge refers to an unknown node")
        degree[edge.source] += 1
        degree[edge.target] += 1
    order = sorted(nodes, key=lambda node: (-degree[node.id], node.id))
    choices = {node.id: _candidate_choices(node, candidate_ids, kg_nodes) for node in order}
    by_pair: dict[tuple[str, str], list[str]] = {}
    for triple in kg_edges:
        by_pair.setdefault((triple.source, triple.target), []).append(triple.relation)
    required = max(1, ceil(0.8 * len(nodes)))
    beam: list[dict[str, str | None]] = [{}]
    expanded = 0
    pruned = False
    for depth, node in enumerate(order):
        next_states: list[tuple[float, dict[str, str | None]]] = []
        for state in beam:
            used = {value for value in state.values() if value is not None}
            for image in choices[node.id]:
                if image is not None and image in used:
                    continue
                new_state = {**state, node.id: image}
                if (
                    sum(value is not None for value in new_state.values()) + len(nodes) - depth - 1
                    < required
                ):
                    continue
                expanded += 1
                if expanded > max_expansions:
                    return SearchOutcome(
                        (), expanded - 1, perf_counter() - started, "budget_exhausted", False
                    )
                next_states.append(
                    (_lower_bound(nodes, edges, kg_nodes, by_pair, new_state), new_state)
                )
        if not next_states:
            return SearchOutcome(
                (), expanded, perf_counter() - started, "no_feasible_mapping", False
            )
        next_states.sort(
            key=lambda item: (
                item[0],
                tuple("~" if v is None else v for _, v in sorted(item[1].items())),
            )
        )
        if len(next_states) > beam_width:
            pruned = True
        beam = [state for _, state in next_states[:beam_width]]
    matches = [_as_match(nodes, edges, kg_nodes, kg_edges, state) for state in beam]
    matches.sort(key=_match_key)
    return SearchOutcome(
        tuple(matches[:top_k]), expanded, perf_counter() - started, "complete", not pruned
    )
