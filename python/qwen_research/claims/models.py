"""Structured claim model.

Claims are first-class persistent entities with project scoping, a typed
vocabulary, an auditable status lifecycle, and explicit provenance. Claims are
created by callers (or, later, model proposals) in a reviewable ``UNREVIEWED``
state — the system never auto-asserts truth. No hidden reasoning is stored.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ClaimId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class ClaimType(StrEnum):
    """A small typed vocabulary for claim classification.

    ``UNKNOWN`` is the default when classification is unavailable; the ontology
    is deliberately not overfit.
    """

    FACTUAL = "factual"
    CAUSAL = "causal"
    COMPARATIVE = "comparative"
    QUANTITATIVE = "quantitative"
    DEFINITIONAL = "definitional"
    PREDICTIVE = "predictive"
    METHODOLOGICAL = "methodological"
    NORMATIVE = "normative"
    UNKNOWN = "unknown"


class ClaimStatus(StrEnum):
    """Memory-promotion / claim lifecycle states.

    These are distinct from truth: ``SUPPORTED`` ≠ ``CORROBORATED`` ≠ ``TRUE``.
    ``UNREVIEWED`` claims are never silently promoted to durable knowledge.
    """

    UNREVIEWED = "unreviewed"
    ASSESSED = "assessed"
    SUPPORTED = "supported"
    CORROBORATED = "corroborated"
    CONTESTED = "contested"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@serializable
@dataclasses.dataclass(frozen=True)
class Scope:
    """A lightweight structured scope object.

    Two claims should not be considered directly contradictory merely because
    their values differ if their scopes clearly differ. All fields are optional.
    """

    population: str | None = None
    conditions: str | None = None
    region: str | None = None
    dataset: str | None = None
    method: str | None = None
    time_range: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class QuantitativeClaim:
    """Structured quantitative claim metadata for deterministic checks."""

    metric: str
    value: float | None = None
    unit: str | None = None
    operator: str | None = None  # "<", "<=", ">", ">=", "=", "!="
    comparison: str | None = None
    population: str | None = None
    time_range: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class Claim:
    """A structured, assertable statement with provenance and lifecycle."""

    claim_id: ClaimId
    project_id: str
    text: str
    type: ClaimType
    status: ClaimStatus
    confidence: float | None
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    supporting_refs: tuple[str, ...]
    contradicting_refs: tuple[str, ...]
    scope: Scope | None
    quantitative: QuantitativeClaim | None
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def create(
        cls,
        project_id: str,
        text: str,
        *,
        claim_type: ClaimType = ClaimType.UNKNOWN,
        source_refs: tuple[str, ...] = (),
        scope: Scope | None = None,
        quantitative: QuantitativeClaim | None = None,
    ) -> Claim:
        now = utc_now()
        return cls(
            claim_id=ClaimId(new_id("claim")),
            project_id=project_id,
            text=text,
            type=claim_type,
            status=ClaimStatus.UNREVIEWED,
            confidence=None,
            source_refs=tuple(source_refs),
            evidence_refs=(),
            supporting_refs=(),
            contradicting_refs=(),
            scope=scope,
            quantitative=quantitative,
            created_at=now,
            updated_at=now,
            version=1,
        )

    def with_status(self, status: ClaimStatus) -> Claim:
        return dataclasses.replace(
            self, status=status, version=self.version + 1, updated_at=utc_now()
        )
