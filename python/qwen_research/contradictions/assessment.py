"""Deterministic contradiction assessment.

Structural, deterministic checks over structured claim metadata (quantitative
values, operators, time ranges, scopes). Open-ended natural-language
contradiction detection is **not** implemented; a future model-assisted layer
will sit behind this same interface.
"""

from __future__ import annotations

import dataclasses
import re

from qwen_research.claims.models import Claim
from qwen_research.contradictions.models import (
    ContradictionStatus,
    ContradictionType,
)


@dataclasses.dataclass(frozen=True)
class ContradictionAssessment:
    """The outcome of comparing two claims."""

    status: ContradictionStatus
    type: ContradictionType
    rationale: str


_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _years(time_range: str | None) -> tuple[int, int] | None:
    if not time_range:
        return None
    years = [int(y) for y in _YEAR_RE.findall(time_range)]
    if not years:
        return None
    return min(years), max(years)


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] < b[0] or b[1] < a[0])


def _values_incompatible(
    value_a: float | None,
    op_a: str | None,
    value_b: float | None,
    op_b: str | None,
) -> bool | None:
    """Return True if the two (operator, value) statements are mutually exclusive,
    False if they are compatible, None if undeterminable."""
    if value_a is None or value_b is None or op_a is None or op_b is None:
        return None
    va, vb = value_a, value_b
    if op_a == "=" and op_b == "=":
        return va != vb
    if op_a == "=" and op_b == "!=":
        return va == vb
    if op_b == "=" and op_a == "!=":
        return va == vb
    # "< x" vs ">= y" is contradictory when y >= x.
    for (lo_op, hi_op, lo_val, hi_val) in (
        ("<", ">=", va, vb),
        ("<=", ">", va, vb),
        (">=", "<", va, vb),
        (">", "<=", va, vb),
    ):
        if op_a == lo_op and op_b == hi_op:
            return hi_val >= lo_val
        if op_b == lo_op and op_a == hi_op:
            return hi_val >= lo_val
    return False


def assess_contradiction(claim_a: Claim, claim_b: Claim) -> ContradictionAssessment:
    """Compare two claims and return a structured assessment.

    Never turns a mere disagreement into ``CONFIRMED``; temporal and scope
    distinctions are resolved first.
    """
    qa, qb = claim_a.quantitative, claim_b.quantitative
    if qa is None or qb is None:
        return ContradictionAssessment(
            ContradictionStatus.INSUFFICIENT_INFORMATION,
            ContradictionType.UNKNOWN,
            "no structured quantitative metadata available for deterministic comparison",
        )

    if qa.metric != qb.metric:
        return ContradictionAssessment(
            ContradictionStatus.NOT_A_CONTRADICTION,
            ContradictionType.DEFINITIONAL_CONFLICT,
            f"different metrics ({qa.metric} vs {qb.metric})",
        )
    if qa.unit and qb.unit and qa.unit != qb.unit:
        return ContradictionAssessment(
            ContradictionStatus.NOT_A_CONTRADICTION,
            ContradictionType.DEFINITIONAL_CONFLICT,
            f"different units ({qa.unit} vs {qb.unit})",
        )

    incompatible = _values_incompatible(qa.value, qa.operator, qb.value, qb.operator)
    if incompatible is None:
        return ContradictionAssessment(
            ContradictionStatus.INSUFFICIENT_INFORMATION,
            ContradictionType.UNKNOWN,
            "insufficient operator/value information to compare",
        )
    if not incompatible:
        return ContradictionAssessment(
            ContradictionStatus.NOT_A_CONTRADICTION,
            ContradictionType.APPARENT_CONTRADICTION,
            "values are compatible",
        )

    # Values are incompatible: check temporal then scope before confirming.
    years_a = _years(qa.time_range or (claim_a.scope.time_range if claim_a.scope else None))
    years_b = _years(qb.time_range or (claim_b.scope.time_range if claim_b.scope else None))
    if years_a is not None and years_b is not None and not _overlap(years_a, years_b):
        return ContradictionAssessment(
            ContradictionStatus.NOT_A_CONTRADICTION,
            ContradictionType.TEMPORAL_CONTRADICTION,
            "apparent conflict is explained by non-overlapping time ranges",
        )

    scope_a = claim_a.scope
    scope_b = claim_b.scope
    if scope_a is not None and scope_b is not None:
        for field in ("population", "region", "dataset"):
            va = getattr(scope_a, field)
            vb = getattr(scope_b, field)
            if va is not None and vb is not None and va != vb:
                return ContradictionAssessment(
                    ContradictionStatus.NOT_A_CONTRADICTION,
                    ContradictionType.SCOPE_CONFLICT,
                    f"apparent conflict is explained by differing scope ({field})",
                )
        if (
            scope_a.method is not None
            and scope_b.method is not None
            and scope_a.method != scope_b.method
        ):
            return ContradictionAssessment(
                ContradictionStatus.POSSIBLE,
                ContradictionType.METHODOLOGICAL_CONFLICT,
                "values conflict but methods differ",
            )

    # Scopes overlap (or are unconstrained) and values conflict → confirmed.
    if scope_a is None and scope_b is None:
        return ContradictionAssessment(
            ContradictionStatus.POSSIBLE,
            ContradictionType.DIRECT_CONTRADICTION,
            "values conflict but no scope information confirms overlap",
        )
    return ContradictionAssessment(
        ContradictionStatus.CONFIRMED,
        ContradictionType.DIRECT_CONTRADICTION,
        "values are mutually exclusive within overlapping scope",
    )
