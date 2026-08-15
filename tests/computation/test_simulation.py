"""Seeded simulation tests."""

from __future__ import annotations

from typing import cast

import pytest

from qwen_research.computation.simulation import simulate
from qwen_research.domain.errors import ComputationValidationError


def _f(value: object) -> float:
    return cast(float, value)


def test_seeded_simulation_is_deterministic() -> None:
    a = simulate(distribution="normal", seed=42, iterations=1000)
    b = simulate(distribution="normal", seed=42, iterations=1000)
    assert a["sample"] == b["sample"]
    assert a["mean"] == b["mean"]


def test_different_seeds_differ() -> None:
    a = simulate(distribution="normal", seed=1, iterations=1000)
    b = simulate(distribution="normal", seed=2, iterations=1000)
    assert a["sample"] != b["sample"]


def test_uniform_bounds() -> None:
    result = simulate(
        distribution="uniform", seed=7, iterations=500,
        parameters={"low": 0.0, "high": 10.0},
    )
    assert _f(result["min"]) >= 0.0
    assert _f(result["max"]) <= 10.0
    assert result["count"] == 500


def test_binomial_range() -> None:
    result = simulate(
        distribution="binomial", seed=3, iterations=100,
        parameters={"n": 5, "p": 0.5},
    )
    assert 0.0 <= _f(result["min"]) <= 5.0
    assert 0.0 <= _f(result["max"]) <= 5.0


def test_unknown_distribution_rejected() -> None:
    with pytest.raises(ComputationValidationError):
        simulate(distribution="weird", seed=1, iterations=10)
