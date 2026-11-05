"""Deterministic soft matching primitives for the E1 protocol.

This module contains no model, database, or network code. It scores one
query-to-candidate mapping so extraction and candidate-generation layers can
be tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
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


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.casefold().replace("_", " ")))


def label_distance(left: str, right: str) -> float:
    """Return token Jaccard distance in [0, 1]. Empty labels are maximally distant."""

    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b) if a and b else 1.0


def _edge_distance(relation: str, candidate: str) -> float:
    return label_distance(relation, candidate)


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

    nodes = list(query_nodes)
    edges = list(query_edges)
    if not nodes:
        raise ValueError("query_nodes must not be empty")
    if not 0 <= node_weight <= 1 or not 0 <= edge_weight <= 1:
        raise ValueError("weights must be in [0, 1]")
    if node_weight + edge_weight == 0:
        raise ValueError("at least one weight must be positive")

    node_cost = 0.0
    for node in nodes:
        target = mapping.get(node.id)
        node_cost += null_node_cost if target is None else label_distance(
            node.label, candidate_nodes[target].label
        )
    node_cost /= len(nodes)

    if edges:
        edge_cost = 0.0
        confidence_mass = 0.0
        candidate_edges = list(candidate_edges)
        for edge in edges:
            confidence = max(0.2, min(1.0, edge.confidence))
            confidence_mass += confidence
            source, target = mapping.get(edge.source), mapping.get(edge.target)
            best = 1.0
            if source is not None and target is not None:
                for triple in candidate_edges:
                    if triple.source == source and triple.target == target:
                        best = min(best, _edge_distance(edge.relation, triple.relation))
            edge_cost += confidence * best
        edge_cost /= confidence_mass
    else:
        edge_cost = 0.0

    total = node_weight + edge_weight
    return (node_weight * node_cost + edge_weight * edge_cost) / total


def validate_mapping(mapping: Mapping[str, str | None]) -> None:
    """Reject duplicate non-null candidate IDs."""

    values = [value for value in mapping.values() if value is not None]
    if len(values) != len(set(values)):
        raise ValueError("mapping must be injective on non-null targets")
