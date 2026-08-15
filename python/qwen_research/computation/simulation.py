"""Seeded, deterministic simulation (SIMULATE).

Supports a small set of distributions and returns summary statistics plus the
sample. The seed is required and persisted; iteration and time limits are
enforced by the caller (the engine) via the execution profile.
"""

from __future__ import annotations

import random
from typing import Any, cast

from qwen_research.computation.descriptive import describe
from qwen_research.domain.errors import ComputationValidationError

_DISTRIBUTIONS = ("uniform", "normal", "binomial", "exponential")


def _f(params: dict[str, object], key: str, default: float) -> float:
    return float(cast(Any, params.get(key, default)))


def _i(params: dict[str, object], key: str, default: int) -> int:
    return int(cast(Any, params.get(key, default)))


def simulate(
    *,
    distribution: str,
    seed: int,
    iterations: int,
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run a seeded simulation and return summary statistics plus the sample.

    ``distribution`` is one of ``uniform``/``normal``/``binomial``/
    ``exponential``; ``parameters`` carries distribution-specific settings.
    The ``seed`` is required for reproducibility.
    """
    if distribution not in _DISTRIBUTIONS:
        raise ComputationValidationError(
            f"unknown distribution {distribution!r} (expected one of {_DISTRIBUTIONS})"
        )
    params = dict(parameters or {})
    rng = random.Random(seed)
    sample: list[float] = []

    if distribution == "uniform":
        lo = _f(params, "low", 0.0)
        hi = _f(params, "high", 1.0)
        sample = [rng.uniform(lo, hi) for _ in range(iterations)]
    elif distribution == "normal":
        mu = _f(params, "mean", 0.0)
        sigma = _f(params, "std", 1.0)
        sample = [rng.gauss(mu, sigma) for _ in range(iterations)]
    elif distribution == "binomial":
        n_trials = _i(params, "n", 10)
        p = _f(params, "p", 0.5)
        sample = [float(_binomial(rng, n_trials, p)) for _ in range(iterations)]
    elif distribution == "exponential":
        rate = _f(params, "rate", 1.0)
        sample = [rng.expovariate(rate) for _ in range(iterations)]

    stats = describe(sample)
    return {
        "distribution": distribution,
        "seed": seed,
        "iterations": iterations,
        "sample": sample,
        **stats,
    }


def _binomial(rng: random.Random, n: int, p: float) -> int:
    """Sample a Binomial(n, p) via the sum of Bernoulli trials (stdlib only)."""
    return sum(1 for _ in range(n) if rng.random() < p)
