"""Contradiction model.

A contradiction is a first-class entity between two claims, with evidence,
type, severity, status, and rationale. Two similar sentences are never assumed
to be contradictory; temporal and scope disagreements are distinguished from
direct contradictions.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ClaimId, ContradictionId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class ContradictionType(StrEnum):
    DIRECT_CONTRADICTION = "direct_contradiction"
    CONTEXTUAL_CONTRADICTION = "contextual_contradiction"
    TEMPORAL_CONTRADICTION = "temporal_contradiction"
    DEFINITIONAL_CONFLICT = "definitional_conflict"
    METHODOLOGICAL_CONFLICT = "methodological_conflict"
    SCOPE_CONFLICT = "scope_conflict"
    APPARENT_CONTRADICTION = "apparent_contradiction"
    UNKNOWN = "unknown"


class ContradictionStatus(StrEnum):
    CONFIRMED = "confirmed"
    POSSIBLE = "possible"
    NOT_A_CONTRADICTION = "not_a_contradiction"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class ContradictionSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@serializable
@dataclasses.dataclass(frozen=True)
class Contradiction:
    """A first-class contradiction between two claims."""

    contradiction_id: ContradictionId
    project_id: str
    claim_a: ClaimId
    claim_b: ClaimId
    evidence_a: str | None
    evidence_b: str | None
    type: ContradictionType
    severity: ContradictionSeverity
    status: ContradictionStatus
    rationale: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        project_id: str,
        claim_a: ClaimId,
        claim_b: ClaimId,
        type_: ContradictionType,
        severity: ContradictionSeverity,
        status: ContradictionStatus,
        rationale: str,
        *,
        evidence_a: str | None = None,
        evidence_b: str | None = None,
    ) -> Contradiction:
        now = utc_now()
        return cls(
            contradiction_id=ContradictionId(new_id("contradiction")),
            project_id=project_id,
            claim_a=claim_a,
            claim_b=claim_b,
            evidence_a=evidence_a,
            evidence_b=evidence_b,
            type=type_,
            severity=severity,
            status=status,
            rationale=rationale,
            created_at=now,
            updated_at=now,
        )
