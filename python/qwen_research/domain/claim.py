"""The Claim domain object."""

from __future__ import annotations

import dataclasses
from enum import StrEnum

from qwen_research.common.ids import ClaimId, EvidenceId, SourceId, new_id
from qwen_research.common.serialization import serializable


class ClaimStatus(StrEnum):
    """Verification standing of a claim."""

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


@serializable
@dataclasses.dataclass(frozen=True)
class Claim:
    """A structured, assertable statement.

    Only the contract exists in Phase 1 — no automatic claim extraction or
    verification is performed.
    """

    claim_id: ClaimId
    text: str
    source_refs: tuple[SourceId, ...]
    evidence_refs: tuple[EvidenceId, ...]
    status: ClaimStatus
    confidence: float | None
    counterevidence_refs: tuple[EvidenceId, ...]

    @classmethod
    def create(
        cls,
        text: str,
        *,
        source_refs: tuple[SourceId, ...] = (),
        evidence_refs: tuple[EvidenceId, ...] = (),
        status: ClaimStatus = ClaimStatus.PROPOSED,
        confidence: float | None = None,
        counterevidence_refs: tuple[EvidenceId, ...] = (),
    ) -> Claim:
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0.0, 1.0]")
        return cls(
            claim_id=ClaimId(new_id("claim")),
            text=text,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            status=status,
            confidence=confidence,
            counterevidence_refs=counterevidence_refs,
        )
