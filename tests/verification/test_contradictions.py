"""Contradiction detection and assessment tests (deterministic, structural)."""

from __future__ import annotations

from qwen_research.claims.models import Claim, ClaimType, QuantitativeClaim, Scope
from qwen_research.contradictions.assessment import assess_contradiction
from qwen_research.contradictions.detector import detect_contradiction, detect_contradictions
from qwen_research.contradictions.models import ContradictionStatus, ContradictionType


def _claim(
    text: str,
    *,
    metric: str = "error_rate",
    value: float = 1.0,
    unit: str = "percent",
    operator: str = "=",
    scope: Scope | None = None,
    time_range: str | None = None,
) -> Claim:
    return Claim.create(
        "p",
        text,
        claim_type=ClaimType.QUANTITATIVE,
        quantitative=QuantitativeClaim(
            metric=metric, value=value, unit=unit, operator=operator, time_range=time_range
        ),
        scope=scope,
    )


def test_direct_quantitative_contradiction() -> None:
    a = _claim("error < 1%", value=1.0, operator="<")
    b = _claim("error >= 5%", value=5.0, operator=">=")
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.POSSIBLE  # no scope overlap info
    assert assessment.type is ContradictionType.DIRECT_CONTRADICTION


def test_direct_contradiction_confirmed_with_scope() -> None:
    scope = Scope(population="surface code")
    a = _claim("error < 1%", value=1.0, operator="<", scope=scope)
    b = _claim("error >= 5%", value=5.0, operator=">=", scope=scope)
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.CONFIRMED
    assert assessment.type is ContradictionType.DIRECT_CONTRADICTION


def test_temporal_disagreement_is_not_contradiction() -> None:
    a = _claim("error < 1%", value=1.0, operator="<", time_range="2018")
    b = _claim("error >= 5%", value=5.0, operator=">=", time_range="2025")
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.NOT_A_CONTRADICTION
    assert assessment.type is ContradictionType.TEMPORAL_CONTRADICTION


def test_scope_disagreement_is_not_contradiction() -> None:
    a = _claim("error < 1%", value=1.0, operator="<", scope=Scope(population="qubits"))
    b = _claim("error >= 5%", value=5.0, operator=">=", scope=Scope(population="gates"))
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.NOT_A_CONTRADICTION
    assert assessment.type is ContradictionType.SCOPE_CONFLICT


def test_equal_values_are_not_contradiction() -> None:
    a = _claim("error = 1%", value=1.0, operator="=")
    b = _claim("error = 1%", value=1.0, operator="=")
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.NOT_A_CONTRADICTION


def test_different_metrics_are_not_contradiction() -> None:
    a = _claim("threshold = 1%", metric="threshold", value=1.0)
    b = _claim("latency = 5%", metric="latency", value=5.0)
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.NOT_A_CONTRADICTION
    assert assessment.type is ContradictionType.DEFINITIONAL_CONFLICT


def test_non_quantitative_claims_insufficient() -> None:
    a = Claim.create("p", "surface codes are promising", claim_type=ClaimType.FACTUAL)
    b = Claim.create("p", "surface codes are not promising", claim_type=ClaimType.FACTUAL)
    assessment = assess_contradiction(a, b)
    assert assessment.status is ContradictionStatus.INSUFFICIENT_INFORMATION


def test_detector_returns_none_for_resolved_disagreement() -> None:
    a = _claim("error < 1%", value=1.0, operator="<", time_range="2018")
    b = _claim("error >= 5%", value=5.0, operator=">=", time_range="2025")
    assert detect_contradiction(a, b) is None


def test_detector_returns_entity_for_confirmed() -> None:
    scope = Scope(population="surface code")
    a = _claim("error < 1%", value=1.0, operator="<", scope=scope)
    b = _claim("error >= 5%", value=5.0, operator=">=", scope=scope)
    contradiction = detect_contradiction(a, b)
    assert contradiction is not None
    assert contradiction.status is ContradictionStatus.CONFIRMED


def test_detect_contradictions_pairwise() -> None:
    scope = Scope(population="surface code")
    a = _claim("error < 1%", value=1.0, operator="<", scope=scope)
    b = _claim("error >= 5%", value=5.0, operator=">=", scope=scope)
    c = _claim("unrelated metric", metric="latency", value=9.0)
    results = detect_contradictions([a, b, c])
    assert len(results) == 1
    assert {results[0].claim_a, results[0].claim_b} == {a.claim_id, b.claim_id}
