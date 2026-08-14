"""Structural contradiction candidate detection.

Identifies potential conflicts between normalized structured claims using
deterministic comparison. Only claims with quantitative metadata are compared;
no natural-language detection is performed.
"""

from __future__ import annotations

from qwen_research.claims.models import Claim
from qwen_research.contradictions.assessment import assess_contradiction
from qwen_research.contradictions.models import (
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
)


def _severity(status: ContradictionStatus) -> ContradictionSeverity:
    if status is ContradictionStatus.CONFIRMED:
        return ContradictionSeverity.ERROR
    if status is ContradictionStatus.POSSIBLE:
        return ContradictionSeverity.WARNING
    return ContradictionSeverity.INFO


def detect_contradiction(claim_a: Claim, claim_b: Claim) -> Contradiction | None:
    """Return a contradiction for two claims, or ``None`` if none is material.

    Only ``CONFIRMED`` and ``POSSIBLE`` assessments produce a contradiction
    entity; temporal/scope/definitional resolutions yield ``None``.
    """
    if claim_a.claim_id == claim_b.claim_id:
        return None
    assessment = assess_contradiction(claim_a, claim_b)
    if assessment.status not in (
        ContradictionStatus.CONFIRMED,
        ContradictionStatus.POSSIBLE,
    ):
        return None
    return Contradiction.create(
        project_id=claim_a.project_id,
        claim_a=claim_a.claim_id,
        claim_b=claim_b.claim_id,
        type_=assessment.type,
        severity=_severity(assessment.status),
        status=assessment.status,
        rationale=assessment.rationale,
    )


def detect_contradictions(claims: list[Claim]) -> list[Contradiction]:
    """Detect structural contradictions across a set of claims (pairwise)."""
    out: list[Contradiction] = []
    for i, claim_a in enumerate(claims):
        for claim_b in claims[i + 1 :]:
            contradiction = detect_contradiction(claim_a, claim_b)
            if contradiction is not None:
                out.append(contradiction)
    return out
