import argparse
import json
import pickle
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_e4_experiment as e4  # noqa: E402

from soft_isomorphism.matching import Triple


def test_query_paths_only_directed_simple_paths():
    graph = {
        "nodes": [{"id": x, "label": x} for x in ("a", "b", "c")],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
            {"source": "c", "target": "a"},
        ],
    }
    assert e4.query_paths(graph) == [(0, 1), (1, 2), (2, 0)]


def test_annotated_path_requires_connected_directed_triples():
    triples = [
        {"source": "Ship", "relation": "builder", "target": "Yard"},
        {"source": "Yard", "relation": "location", "target": "City"},
    ]
    assert e4.has_annotated_path("Ship", ["builder", "location"], triples)
    assert e4.has_annotated_path("City", ["~location", "~builder"], triples)
    assert not e4.has_annotated_path("Ship", ["location", "builder"], triples)


def test_rerank_preserves_b1_evidence_when_mapping_fails():
    row = {
        "id": "missing",
        "text": "claim",
        "graph": {"nodes": [], "edges": []},
        "status": "empty_graph",
        "mappings": [],
        "b1_evidence": [{"source": "A", "relation": "r", "target": "B"}],
    }
    result = e4.rerank_row(row, lambda _left, _right: 1.0)
    assert result["arms"]["B4"]["status"] == "empty_graph"
    assert result["arms"]["E4"]["evidence"] == []
    assert result["b1_evidence"] == row["b1_evidence"]


def test_path_penalty_changes_mapping_with_same_semantic_candidates():
    graph = {
        "nodes": [
            {"id": "s", "label": "a"},
            {"id": "m", "label": "d"},
            {"id": "t", "label": "c"},
        ],
        "edges": [
            {"source": "s", "relation": "r1", "target": "m"},
            {"source": "m", "relation": "r2", "target": "t"},
        ],
    }
    row = {
        "id": "example",
        "text": "example",
        "graph": graph,
        "status": "ok",
        "mappings": [
            {"s": "a", "m": "b", "t": "c"},
            {"s": "a", "m": "d", "t": "c"},
        ],
        "pool_triples": [
            Triple("a", "p1", "b").__dict__,
            Triple("b", "p2", "c").__dict__,
            Triple("a", "r1", "d").__dict__,
        ],
        "b1_evidence": [],
    }
    scores = {("r1", "p1"): 0.6, ("r2", "p2"): 0.6, ("r1", "r1"): 1.0}
    result = e4.rerank_row(row, lambda left, right: scores[left, right])
    assert result["arms"]["B4"]["mapping"]["m"] == "d"
    assert result["arms"]["E4"]["mapping"]["m"] == "b"
    assert result["arms"]["B4"]["complete_paths"] == 0
    assert result["arms"]["E4"]["complete_paths"] == 1
    assert len(result["arms"]["E4"]["evidence"]) == 2


def test_reader_reuses_identical_evidence_across_arms(tmp_path, monkeypatch):
    data_dir = tmp_path / "factkg"
    data_dir.mkdir()
    with (data_dir / "factkg_dev.pickle").open("wb") as stream:
        pickle.dump({"claim": {"Label": [True]}}, stream)
    evidence = [{"source": "A", "relation": "r", "target": "B"}]
    row = {
        "id": e4.digest("claim"),
        "text": "claim",
        "b1_evidence": evidence,
        "arms": {"B4": {"evidence": evidence}, "E4": {"evidence": evidence}},
    }
    e4.write_jsonl(tmp_path / "reranked.jsonl", [row])
    calls = []

    def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps({"verdict": "TRUE"}), {}, 0.1

    monkeypatch.setattr(e4, "call_model", fake_call)
    args = argparse.Namespace(
        out_dir=tmp_path,
        data_dir=data_dir,
        split="dev",
        model="fake-model",
        server_url="http://example.invalid",
        reader_max_tokens=256,
        kilo_auth_provider=None,
        api_key_env="UNSET_TEST_KEY",
        json_mode="object",
    )
    e4.read(args)
    summary = json.loads((tmp_path / "reader-summary.json").read_text())
    assert len(calls) == 1
    assert all(summary["arms"][arm]["accuracy"] == 1.0 for arm in ("B1", "B4", "E4"))
    row["arms"]["E4"]["evidence"] = []
    e4.write_jsonl(tmp_path / "reranked.jsonl", [row])
    with pytest.raises(ValueError, match="different evidence"):
        e4.read(args)
