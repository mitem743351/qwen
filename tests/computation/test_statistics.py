"""Deterministic statistics unit tests (pure stdlib)."""

from __future__ import annotations

from qwen_research.computation.descriptive import (
    describe,
    linear_regression,
    pearson_correlation,
    quantiles,
)


def test_describe_basic() -> None:
    stats = describe([1.0, 2.0, 3.0, 4.0])
    assert stats["count"] == 4
    assert stats["mean"] == 2.5
    assert stats["median"] == 2.5
    assert stats["min"] == 1.0
    assert stats["max"] == 4.0
    assert stats["sum"] == 10.0


def test_describe_missing_values_excluded() -> None:
    stats = describe([1.0, None, 2.0, None, 3.0])
    assert stats["count"] == 3
    assert stats["missing"] == 2
    assert stats["nan_count"] == 2


def test_describe_nan_and_inf_flagged() -> None:
    stats = describe([1.0, float("nan"), float("inf"), 2.0])
    assert stats["count"] == 2
    assert stats["nan_count"] == 1
    assert stats["inf_count"] == 1


def test_quantiles_default_quartiles() -> None:
    assert quantiles([1.0, 2.0, 3.0, 4.0]) == [1.75, 2.5, 3.25]


def test_pearson_correlation_perfect() -> None:
    result = pearson_correlation([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
    assert result["correlation"] == 1.0
    assert result["sample_count"] == 3


def test_pearson_correlation_missing_pairs() -> None:
    result = pearson_correlation([1.0, None, 3.0], [2.0, 4.0, 6.0])
    assert result["sample_count"] == 2
    assert result["missing"] == 1


def test_linear_regression_slope() -> None:
    result = linear_regression([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
    assert result["slope"] == 2.0
    assert result["intercept"] == 0.0
    assert result["r_squared"] == 1.0


def test_regression_insufficient_data() -> None:
    result = linear_regression([1.0], [2.0])
    assert result["slope"] is None
