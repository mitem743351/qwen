"""Neutral verification repository interfaces.

The Research Runtime / VerificationEngine depend on these protocols; SQL lives
only inside the repository implementation. Project scoping is enforced at
these query boundaries.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.claims.models import Claim
from qwen_research.claims.relationships import ClaimEvidenceLink
from qwen_research.contradictions.models import Contradiction
from qwen_research.sources.quality import SourceQuality
from qwen_research.verification.models import EvidenceAssessment, VerificationReport


@runtime_checkable
class ClaimRepository(Protocol):
    def save_claim(self, claim: Claim) -> None: ...
    def update_claim(self, claim: Claim) -> None: ...
    def get_claim(self, claim_id: str) -> Claim | None: ...
    def get_claims(self, project_id: str) -> list[Claim]: ...


@runtime_checkable
class ClaimEvidenceRepository(Protocol):
    def save_link(self, link: ClaimEvidenceLink) -> None: ...
    def get_links(self, claim_id: str) -> list[ClaimEvidenceLink]: ...


@runtime_checkable
class EvidenceAssessmentRepository(Protocol):
    def save_assessment(self, assessment: EvidenceAssessment) -> None: ...
    def get_assessments(self, claim_id: str) -> list[EvidenceAssessment]: ...


@runtime_checkable
class ContradictionRepository(Protocol):
    def save_contradiction(self, contradiction: Contradiction) -> None: ...
    def get_contradictions(self, project_id: str) -> list[Contradiction]: ...
    def get_contradictions_for_claim(self, claim_id: str) -> list[Contradiction]: ...


@runtime_checkable
class VerificationRepository(Protocol):
    def save_report(self, report: VerificationReport) -> None: ...
    def get_report(self, report_id: str) -> VerificationReport | None: ...
    def get_reports(self, project_id: str) -> list[VerificationReport]: ...


@runtime_checkable
class SourceQualityRepository(Protocol):
    def save_source_quality(self, source_id: str, quality: SourceQuality) -> None: ...
    def get_source_quality(self, source_id: str) -> SourceQuality | None: ...


@runtime_checkable
class VerificationStore(
    ClaimRepository,
    ClaimEvidenceRepository,
    EvidenceAssessmentRepository,
    ContradictionRepository,
    VerificationRepository,
    SourceQualityRepository,
    Protocol,
):
    """A store implementing all verification repositories."""

    def initialize(self) -> None: ...
    def close(self) -> None: ...
