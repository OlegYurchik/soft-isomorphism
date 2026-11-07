"""Deterministic soft matching primitives for the E1 protocol.

This module contains no model, database, or network code. It scores one
query-to-candidate mapping so extraction and candidate-generation layers can
be tested independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import ceil, isfinite
from typing import Iterable, Mapping

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Node:
    id: str
    label: str


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    confidence: float = 1.0


@dataclass(frozen=True)
class Triple:
    source: str
    relation: str
    target: str


@dataclass(frozen=True)
class CostBreakdown:
    node: float
    edge: float
    total: float
    matched_nodes: int
    query_nodes: int


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.casefold().replace("_", " ")))


def label_distance(left: str, right: str) -> float:
    """Return character-trigram Jaccard distance for entity labels."""

    def trigrams(value: str) -> set[str]:
        normalized = " ".join(value.casefold().replace("_", " ").split())
        return {normalized[i : i + 3] for i in range(len(normalized) - 2)} or (
            {normalized} if normalized else set()
        )

    a, b = trigrams(left), trigrams(right)
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b) if a and b else 1.0


def _edge_distance(relation: str, candidate: str) -> float:
    a, b = _tokens(relation), _tokens(candidate)
    if not a or not b:
        return 1.0
    return 1.0 - len(a & b) / len(a | b)


def score_mapping(
    query_nodes: Iterable[Node],
    query_edges: Iterable[Edge],
    candidate_nodes: Mapping[str, Node],
    candidate_edges: Iterable[Triple],
    mapping: Mapping[str, str | None],
    *,
    node_weight: float = 0.3,
    edge_weight: float = 0.7,
    null_node_cost: float = 0.8,
) -> float:
    """Score an asymmetric query -> KG mapping using the E1 normalized cost.

    Candidate edges may contain additional facts. Missing query edges receive
    distance 1 and are weighted by extraction confidence. A null mapping receives
    null_node_cost; callers can enforce injectivity separately.
    """

    return score_mapping_breakdown(
        query_nodes,
        query_edges,
        candidate_nodes,
        candidate_edges,
        mapping,
        node_weight=node_weight,
        edge_weight=edge_weight,
        null_node_cost=null_node_cost,
    ).total


def score_mapping_breakdown(
    query_nodes: Iterable[Node],
    query_edges: Iterable[Edge],
    candidate_nodes: Mapping[str, Node],
    candidate_edges: Iterable[Triple],
    mapping: Mapping[str, str | None],
    *,
    node_weight: float = 0.3,
    edge_weight: float = 0.7,
    null_node_cost: float = 0.8,
) -> CostBreakdown:
    """Score a complete directed mapping; extra KG triples incur no penalty."""
    nodes = list(query_nodes)
    edges = list(query_edges)
    if not nodes:
        raise ValueError("query_nodes must not be empty")
    if not all(isfinite(x) for x in (node_weight, edge_weight, null_node_cost)):
        raise ValueError("cost parameters must be finite")
    if not 0 <= node_weight <= 1 or not 0 <= edge_weight <= 1:
        raise ValueError("weights must be in [0, 1]")
    if node_weight + edge_weight == 0:
        raise ValueError("at least one weight must be positive")
    if not 0 <= null_node_cost <= 1:
        raise ValueError("null_node_cost must be in [0, 1]")
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes) or set(mapping) != node_ids:
        raise ValueError("mapping must contain each distinct query node exactly once")
    validate_mapping(mapping)
    if any(target is not None and target not in candidate_nodes for target in mapping.values()):
        raise ValueError("mapping refers to an unknown candidate node")
    matched_nodes = sum(target is not None for target in mapping.values())
    if matched_nodes < max(1, ceil(0.8 * len(nodes))):
        raise ValueError("mapping violates the minimum 80% node coverage")
    if any(edge.source not in node_ids or edge.target not in node_ids for edge in edges):
        raise ValueError("query edge refers to an unknown node")
    if any(not isfinite(edge.confidence) or edge.confidence < 0 for edge in edges):
        raise ValueError("edge confidence must be finite and non-negative")

    node_cost = 0.0
    for node in nodes:
        target = mapping.get(node.id)
        node_cost += (
            null_node_cost
            if target is None
            else (
                0.0
                if node.label == "?"
                else label_distance(node.label, candidate_nodes[target].label)
            )
        )
    node_cost /= len(nodes)

    if edges:
        edge_cost = 0.0
        confidence_mass = 0.0
        by_pair: dict[tuple[str, str], list[str]] = {}
        for triple in candidate_edges:
            by_pair.setdefault((triple.source, triple.target), []).append(triple.relation)
        for edge in edges:
            confidence = max(0.2, min(1.0, edge.confidence))
            confidence_mass += confidence
            source, target = mapping.get(edge.source), mapping.get(edge.target)
            best = 1.0
            if source is not None and target is not None:
                for relation in by_pair.get((source, target), ()):
                    best = min(best, _edge_distance(edge.relation, relation))
            edge_cost += confidence * best
        edge_cost /= confidence_mass
    else:
        edge_cost = 0.0

    if not edges:
        return CostBreakdown(node_cost, 0.0, node_cost, matched_nodes, len(nodes))
    total = node_weight + edge_weight
    return CostBreakdown(
        node_cost,
        edge_cost,
        (node_weight * node_cost + edge_weight * edge_cost) / total,
        matched_nodes,
        len(nodes),
    )


def validate_mapping(mapping: Mapping[str, str | None]) -> None:
    """Reject duplicate non-null candidate IDs."""

    values = [value for value in mapping.values() if value is not None]
    if len(values) != len(set(values)):
        raise ValueError("mapping must be injective on non-null targets")
