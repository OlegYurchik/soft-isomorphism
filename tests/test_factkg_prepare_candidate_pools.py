import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import factkg_prepare_candidate_pools as pools  # noqa: E402


def test_empty_graph_skips_pool_search():
    row = {
        "id": "empty",
        "text": "claim",
        "graph": {"nodes": [], "edges": []},
    }

    result = pools.build_pool_row(row, {}, None)

    assert result["status"] == "empty_graph"
    assert result["pool_triples"] == []
    assert result["candidate_ids"] == {}
    assert result["b1_evidence"] == []
    assert result["pool_wall_seconds"] >= 0
    assert result["pool_cpu_seconds"] >= 0
