"""Claim–evidence relationship model.

The semantic meaning of "this evidence bears on this claim" is carried by an
explicit link, not by a bare ``evidence_refs`` list. Each link records a
relationship, a rationale, and a review status.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ClaimId, EvidenceId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class ClaimEvidenceRelationship(StrEnum):
    """How an evidence item relates to a claim."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"
    CONTEXTUALIZES = "contextualizes"
    DOES_NOT_ADDRESS = "does_not_address"


class LinkStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


@serializable
@dataclasses.dataclass(frozen=True)
class ClaimEvidenceLink:
    """An explicit claim–evidence relationship."""

    link_id: str
    claim_id: ClaimId
    evidence_id: EvidenceId
    relationship: ClaimEvidenceRelationship
    rationale: str
    status: LinkStatus
    created_at: datetime

    @classmethod
    def create(
        cls,
        claim_id: ClaimId,
        evidence_id: EvidenceId,
        relationship: ClaimEvidenceRelationship,
        rationale: str = "",
    ) -> ClaimEvidenceLink:
        return cls(
            link_id=new_id("link"),
            claim_id=claim_id,
            evidence_id=evidence_id,
            relationship=relationship,
            rationale=rationale,
            status=LinkStatus.ACTIVE,
            created_at=utc_now(),
        )
