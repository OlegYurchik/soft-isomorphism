import importlib.util
import json
import pickle
import sqlite3
from pathlib import Path

from soft_isomorphism.matching import Edge, Node, Triple
from soft_isomorphism.search import exhaustive_search

SCRIPT = Path(__file__).parents[1] / "scripts" / "factkg_e1_pilot.py"
spec = importlib.util.spec_from_file_location("factkg_e1_pilot", SCRIPT)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_selected_claims_supports_stable_offset(tmp_path):
    path = tmp_path / "claims.pickle"
    claims = {"gamma": {}, "alpha": {}, "beta": {}}
    with path.open("wb") as stream:
        pickle.dump(claims, stream)
    expected = sorted(claims, key=pilot.digest)[1:3]
    assert pilot.selected_claims(path, limit=2, offset=1) == expected


def test_merge_views_uses_agreement_not_gold():
    claim = "Alice wrote Book."
    raw = json.dumps(
        {
            "nodes": [{"id": "a", "label": "Alice"}, {"id": "b", "label": "Book"}],
            "edges": [
                {
                    "source": "a",
                    "relation": "author",
                    "target": "b",
                    "polarity": "positive",
                    "quote": "Alice wrote Book",
                }
            ],
        }
    )
    view = pilot.parse_view(raw, claim)
    graph = pilot.merge_views([view, view, []])
    assert graph["edges"][0]["confidence"] == 2 / 3
    assert not any(key in graph for key in ("Label", "Evidence", "Entity_set"))


def test_single_extraction_view_has_unit_weight():
    graph = pilot.merge_views([[("alice", "author", "book", "positive")]])
    assert graph["edges"][0]["confidence"] == 1.0


def test_uniform_weights_make_b3_and_e1_identical():
    graph = pilot.merge_views([[("a", "r1", "c", "positive"), ("a", "r2", "c", "positive")]])
    assert {edge["confidence"] for edge in graph["edges"]} == {1.0}
    nodes = [Node(item["id"], item["label"]) for item in graph["nodes"]]
    kg_nodes = {label: Node(label, label) for label in ("a", "b", "c")}
    kg_edges = [Triple("a", "r1", "b"), Triple("a", "r2", "c")]
    candidates = {node.id: [node.label] if node.label == "a" else ["b", "c"] for node in nodes}

    arms = {}
    for arm in ("B3", "E1"):
        edges = [
            Edge(
                item["source"],
                item["relation"],
                item["target"],
                item["confidence"] if arm == "E1" else 1.0,
            )
            for item in graph["edges"]
        ]
        outcome = exhaustive_search(nodes, edges, kg_nodes, kg_edges, candidates)
        arms[arm] = (
            outcome.matches,
            pilot.evidence(outcome.matches[0].mapping, graph, kg_edges, weighted=arm == "E1"),
        )
    assert arms["B3"] == arms["E1"]


def test_nonuniform_weights_can_change_the_best_mapping():
    nodes = [Node("s", "a"), Node("t", "c")]
    kg_nodes = {label: Node(label, label) for label in ("a", "b", "c")}
    kg_edges = [Triple("a", "r1", "b"), Triple("a", "r2", "c")]
    candidates = {"s": ["a"], "t": ["b", "c"]}
    b3 = [Edge("s", "r1", "t", 1), Edge("s", "r2", "t", 1)]
    e1 = [Edge("s", "r1", "t", 1), Edge("s", "r2", "t", 1 / 3)]
    b3_best = exhaustive_search(nodes, b3, kg_nodes, kg_edges, candidates).matches[0]
    e1_best = exhaustive_search(nodes, e1, kg_nodes, kg_edges, candidates).matches[0]
    assert b3_best.mapping == {"s": "a", "t": "c"}
    assert e1_best.mapping == {"s": "a", "t": "b"}


def test_parse_view_rejects_nonliteral_quote():
    claim = "Alice wrote Book."
    raw = json.dumps(
        {
            "nodes": [{"id": "a", "label": "Alice"}, {"id": "b", "label": "Book"}],
            "edges": [
                {
                    "source": "a",
                    "relation": "author",
                    "target": "b",
                    "polarity": "positive",
                    "quote": "Alice authored Book",
                }
            ],
        }
    )
    try:
        pilot.parse_view(raw, claim)
    except ValueError as error:
        assert "quote" in str(error)
    else:
        raise AssertionError("nonliteral quote was accepted")


def test_parse_view_uses_grounded_id_when_label_is_generic_type():
    raw = json.dumps(
        {
            "nodes": [
                {"id": "Adam Koc", "label": "Person"},
                {"id": "Virtuti Militari", "label": "Award"},
            ],
            "edges": [
                {
                    "source": "Adam Koc",
                    "relation": "awards",
                    "target": "Virtuti Militari",
                    "polarity": "positive",
                    "quote": "awarded the Virtuti Militari",
                }
            ],
        }
    )
    edges = pilot.parse_view(raw, "Adam Koc was awarded the Virtuti Militari.", {"awards"})
    assert edges[0][:3] == ("adam koc", "awards", "virtuti militari")


def test_parse_view_accepts_numeric_ids_and_unnamed_endpoint():
    raw = json.dumps(
        {
            "nodes": [{"id": 0, "label": "Helsinki"}],
            "edges": [
                {
                    "source": 0,
                    "relation": "country",
                    "target": "?",
                    "polarity": "positive",
                    "quote": "Helsinki, a country",
                }
            ],
        }
    )
    assert pilot.parse_view(raw, "Helsinki, a country") == [
        ("helsinki", "country", "?", "positive")
    ]


def test_qwen38_request_disables_thinking(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, *_):
            return b'{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        captured["user_agent"] = request.headers["User-agent"]
        return Response()

    monkeypatch.setattr(pilot.urllib.request, "urlopen", fake_urlopen)
    pilot.call_model(
        "https://example.test", "Return JSON", "Claim", 32, model="iairlab/qwen3.8-27b"
    )
    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["messages"][1]["content"] == "Claim"
    assert captured["user_agent"] == "OpenAI/Python 1.0"


def test_candidate_pool_preserves_reverse_relation_direction():
    kg = {"Alice": {"author": ["Book"]}, "Book": {"~author": ["Alice"]}}
    graph = {"nodes": [{"id": "n0", "label": "Alice"}, {"id": "n1", "label": "Book"}], "edges": []}
    _, triples, candidates = pilot.candidate_pool(kg, graph, "Alice wrote Book")
    assert Triple("Alice", "author", "Book") in triples
    assert Triple("Book", "author", "Alice") not in triples
    assert candidates == {"n0": ["Alice"], "n1": ["Book"]}


def test_fts_linking_finds_normalized_name():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE VIRTUAL TABLE entity_names USING fts5(id UNINDEXED, label, tokenize='trigram')"
    )
    connection.executemany(
        "INSERT INTO entity_names(id,label) VALUES(?,?)",
        [
            ("Taylor_County,_Texas", "taylor county, texas"),
            ("Taylor_County,_Iowa", "taylor county, iowa"),
        ],
    )
    assert pilot.link_candidates(connection, "Taylor County, Texas")[0] == "Taylor_County,_Texas"


def test_fts_linking_recovers_accented_surname_from_first_name():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE VIRTUAL TABLE entity_names USING fts5(id UNINDEXED, label, tokenize='trigram')"
    )
    connection.executemany(
        "INSERT INTO entity_names(id,label) VALUES(?,?)",
        [
            ("Sauli_Niinistö", "sauli niinistö"),
            ("niinisto.fi", "niinisto.fi"),
        ],
    )
    assert pilot.link_candidates(connection, "Sauli Niinisto")[0] == "Sauli_Niinistö"


def test_direct_id_variant_recovers_name_after_article():
    kg = {"National_Park_Service": {}}
    assert pilot.direct_id_variants("the national park service", kg) == ["National_Park_Service"]


def test_variable_candidates_prefer_relation_connected_entity():
    graph = {
        "nodes": [{"id": "n0", "label": "Helsinki"}, {"id": "n1", "label": "?"}],
        "edges": [{"source": "n0", "relation": "country", "target": "n1"}],
    }
    triples = [
        Triple("Helsinki", "timeZone", "Europe"),
        Triple("Helsinki", "country", "Finland"),
        Triple("Helsinki", "country", '"Finland"'),
    ]
    assert pilot.variable_candidates("n1", graph, triples, {"n0": ["Helsinki"]}, {"Helsinki"}) == [
        "Finland",
        "Europe",
    ]


def test_bm25_fanout_prioritizes_claim_relation():
    triples = [Triple("Alice", "award", "Medal"), Triple("Alice", "birthPlace", "Paris")]
    ranked = pilot.bm25_incident(triples, "Alice was born in Paris", limit=1)
    assert ranked == [Triple("Alice", "birthPlace", "Paris")]


def test_counterevidence_returns_actual_alternative_relation_value():
    graph = {
        "edges": [
            {
                "source": "n0",
                "relation": "leaderTitle",
                "target": "n1",
                "confidence": 1.0,
            }
        ]
    }
    mapping = {"n0": "Israel", "n1": "Metropolitan_Commissioner"}
    triples = [
        Triple("Israel", "leaderTitle", "President"),
        Triple("Israel", "capital", "Jerusalem"),
    ]
    assert pilot.evidence(mapping, graph, triples) == []
    assert pilot.evidence(mapping, graph, triples, counterevidence=True) == [
        {"source": "Israel", "relation": "leaderTitle", "target": "President"}
    ]


def test_expanded_evidence_uses_real_reverse_and_alternative_facts():
    kg = {
        "Israel": {"leaderTitle": ["President"], "capital": ["Jerusalem"]},
        "Ciudad_Ayala": {"leaderName": ["Juan_Nolasco"]},
        "Juan_Nolasco": {"~leaderName": ["Ciudad_Ayala"]},
    }
    graph = {
        "nodes": [
            {"id": "s", "label": "Israel"},
            {"id": "t", "label": "Metropolitan Commissioner"},
        ],
        "edges": [
            {
                "source": "s",
                "relation": "leader title",
                "target": "t",
                "confidence": 1.0,
            }
        ],
    }
    assert pilot.expanded_evidence(kg, {"s": "Israel", "t": None}, graph) == [
        {"source": "Israel", "relation": "leaderTitle", "target": "President"}
    ]
    reverse_graph = {
        "nodes": [
            {"id": "s", "label": "Juan Nolasco"},
            {"id": "t", "label": "Ciudad Ayala"},
        ],
        "edges": [{"source": "s", "relation": "leader of", "target": "t", "confidence": 1.0}],
    }
    assert pilot.expanded_evidence(
        kg, {"s": "Juan_Nolasco", "t": "Ciudad_Ayala"}, reverse_graph
    ) == [{"source": "Ciudad_Ayala", "relation": "leaderName", "target": "Juan_Nolasco"}]


def test_hybrid_falls_back_only_on_unknown():
    assert pilot.fallback_verdict("UNKNOWN", False) == ("FALSE", "B0")
    assert pilot.fallback_verdict("UNKNOWN", True) == ("TRUE", "B0")
    assert pilot.fallback_verdict("FALSE", True) == ("FALSE", "graph")
