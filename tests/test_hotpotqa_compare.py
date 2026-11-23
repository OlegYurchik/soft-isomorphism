import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from hotpotqa_compare import (  # noqa: E402
    bootstrap_interval,
    direction_counts,
    exact_binary_pvalue,
    sign_flip_pvalue,
)


def test_direction_counts_and_exact_binary_test() -> None:
    assert direction_counts([1.0, 0.0, -0.5]) == {"improved": 1, "regressed": 1, "tied": 1}
    assert exact_binary_pvalue(5, 2) == pytest.approx(0.453125)


def test_sign_flip_and_bootstrap_are_deterministic() -> None:
    deltas = [1.0, 1.0, -1.0, 0.0]
    assert sign_flip_pvalue(deltas) == sign_flip_pvalue(deltas)
    assert bootstrap_interval(deltas) == bootstrap_interval(deltas)
    assert sign_flip_pvalue([0.0, 0.0]) == 1.0
