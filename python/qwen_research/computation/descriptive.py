"""Deterministic numerical statistics (pure stdlib).

A small, reproducible baseline for ``count``/``sum``/``mean``/``median``/
``min``/``max``/``std``/``variance``/``quantiles``/``correlation`` and a
minimal linear regression. Missing values (``None``) are excluded; non-finite
values (``NaN``/``inf``) are reported explicitly rather than silently
propagated. Numerical conventions are documented inline; no causality is ever
implied by correlation/regression.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import fmean, median, stdev, variance


def _finite(values: Sequence[float | None]) -> tuple[list[float], int, int]:
    """Split values into finite values and counts of non-finite/missing.

    Returns ``(finite, nan_count, inf_count)``. ``None``/``NaN`` are excluded
    from the finite list; infinities are excluded too (they are flagged, never
    used in a mean).
    """
    finite: list[float] = []
    nan_count = 0
    inf_count = 0
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            nan_count += 1
            continue
        if isinstance(v, float) and math.isinf(v):
            inf_count += 1
            continue
        finite.append(float(v))
    return finite, nan_count, inf_count


def describe(values: Sequence[float | None]) -> dict[str, object]:
    """Return deterministic summary statistics for a list of numeric values."""
    finite, nan_count, inf_count = _finite(values)
    n = len(finite)
    if n == 0:
        return {
            "count": 0,
            "missing": nan_count + inf_count,
            "nan_count": nan_count,
            "inf_count": inf_count,
        }
    srt = sorted(finite)
    return {
        "count": n,
        "missing": nan_count + inf_count,
        "nan_count": nan_count,
        "inf_count": inf_count,
        "sum": round(sum(finite), 12),
        "mean": round(fmean(finite), 12),
        "median": round(median(finite), 12),
        "min": srt[0],
        "max": srt[-1],
        "std": round(stdev(finite), 12) if n > 1 else 0.0,
        "variance": round(variance(finite), 12) if n > 1 else 0.0,
        "quantiles": quantiles(finite),
    }


def quantiles(values: list[float], n: int = 4) -> list[float]:
    """Return ``n-1`` evenly spaced quantiles (default quartiles)."""
    if len(values) == 0:
        return []
    srt = sorted(values)
    out: list[float] = []
    for k in range(1, n):
        idx = (len(srt) - 1) * k / n
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        frac = idx - lo
        out.append(round(srt[lo] * (1 - frac) + srt[hi] * frac, 12))
    return out


def pearson_correlation(
    xs: Sequence[float | None], ys: Sequence[float | None]
) -> dict[str, object]:
    """Pearson correlation with explicit missing-value handling.

    Rows where either coordinate is missing/non-finite are dropped; the sample
    count is reported. The result is labelled a *correlation*, never a causal
    relationship.
    """
    if len(xs) != len(ys):
        raise ValueError("x and y must have the same length")
    pairs = [
        (float(x), float(y))
        for x, y in zip(xs, ys, strict=True)
        if x is not None
        and y is not None
        and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))
        and not (isinstance(y, float) and (math.isnan(y) or math.isinf(y)))
    ]
    n = len(pairs)
    if n < 2:
        return {"sample_count": n, "correlation": None, "missing": len(xs) - n}
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    sx = stdev(x)
    sy = stdev(y)
    if sx == 0 or sy == 0:
        return {"sample_count": n, "correlation": 0.0, "missing": len(xs) - n}
    mx = fmean(x)
    my = fmean(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (n - 1)
    r = cov / (sx * sy)
    return {
        "sample_count": n,
        "missing": len(xs) - n,
        "correlation": round(max(-1.0, min(1.0, r)), 12),
    }


def linear_regression(xs: Sequence[float | None], ys: Sequence[float | None]) -> dict[str, object]:
    """Least-squares linear regression (y ~ x).

    Returns slope, intercept, R², sample count, and residual metrics. This is
    descriptive only — it does **not** imply causality.
    """
    if len(xs) != len(ys):
        raise ValueError("x and y must have the same length")
    pairs = [
        (float(x), float(y))
        for x, y in zip(xs, ys, strict=True)
        if x is not None
        and y is not None
        and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))
        and not (isinstance(y, float) and (math.isnan(y) or math.isinf(y)))
    ]
    n = len(pairs)
    if n < 2:
        return {"sample_count": n, "slope": None, "intercept": None, "r_squared": None}
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    mx = fmean(x)
    my = fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        return {"sample_count": n, "slope": None, "intercept": None, "r_squared": None}
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    slope = sxy / sxx
    intercept = my - slope * mx
    residuals = [b - (slope * a + intercept) for a, b in zip(x, y, strict=True)]
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((b - my) ** 2 for b in y)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else None
    return {
        "sample_count": n,
        "slope": round(slope, 12),
        "intercept": round(intercept, 12),
        "r_squared": round(r_squared, 12) if r_squared is not None else None,
        "residual_mean_abs": round(fmean([abs(r) for r in residuals]), 12),
        "residual_std": round(stdev(residuals), 12) if n > 2 else 0.0,
    }
