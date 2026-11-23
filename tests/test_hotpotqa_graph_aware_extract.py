import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_graph_aware_extract import seed_titles  # noqa: E402

from soft_isomorphism.hotpotqa import HotpotInput, Sentence  # noqa: E402


def example() -> HotpotInput:
    return HotpotInput(
        "id",
        "Which hotel hosted WrestleMania IX?",
        (
            Sentence("Distractor", 0, "A hotel hosted an event."),
            Sentence("WrestleMania IX", 0, "It took place at Caesars Palace."),
        ),
    )


def test_seed_titles_prefer_exact_query_entity_title() -> None:
    graph = {
        "nodes": [{"id": "n0", "label": "wrestlemania ix"}],
        "edges": [],
    }
    assert seed_titles(example(), graph, 4) == ["WrestleMania IX"]


def test_seed_titles_fall_back_to_one_bm25_title() -> None:
    graph = {"nodes": [{"id": "n0", "label": "absent entity"}], "edges": []}
    assert len(seed_titles(example(), graph, 4)) == 1
