"""The VerificationResult domain object."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ClaimId, VerificationId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class VerificationStatus(StrEnum):
    """Outcome of a verification pass."""

    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


@serializable
@dataclasses.dataclass(frozen=True)
class VerificationResult:
    """The structured outcome of verifying a claim.

    Only the contract exists in Phase 1; the verification engine is future.
    """

    verification_id: VerificationId
    claim_id: ClaimId
    status: VerificationStatus
    findings: tuple[str, ...] = ()
    created_at: datetime = dataclasses.field(default_factory=utc_now)

    @classmethod
    def create(
        cls, claim_id: ClaimId, status: VerificationStatus, findings: tuple[str, ...] = ()
    ) -> VerificationResult:
        return cls(
            verification_id=VerificationId(new_id("verification")),
            claim_id=claim_id,
            status=status,
            findings=findings,
        )
