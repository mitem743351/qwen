"""Verification models: status, issues, reports, coverage, and assessment.

Verification is scoped and **never absolute**: ``VERIFIED_WITHIN_CORPUS`` means
"passed the configured deterministic procedures against the currently indexed
corpus", not "true". The word ``VERIFIED`` is never used unqualified.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from qwen_research.common.ids import (
    ClaimId,
    EvidenceAssessmentId,
    EvidenceId,
    VerificationReportId,
    new_id,
)
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.evidence.models import EvidenceQuality, SupportType


class VerificationStatus(StrEnum):
    """Scoped, non-absolute verification states."""

    UNREVIEWED = "unreviewed"
    RETRIEVED = "retrieved"
    ASSESSED = "assessed"
    PARTIALLY_SUPPORTED = "partially_supported"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VERIFIED_WITHIN_CORPUS = "verified_within_corpus"


class Severity(StrEnum):
    """Issue severity. ``CRITICAL`` means a serious verification problem, not falsehood."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class VerificationScope(StrEnum):
    SOURCE = "source"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    RESEARCH_STATE = "research_state"
    PROJECT = "project"


@serializable
@dataclasses.dataclass(frozen=True)
class VerificationIssue:
    """A single deterministic verification finding."""

    code: str
    severity: Severity
    entity_type: str
    entity_id: str
    message: str


@serializable
@dataclasses.dataclass(frozen=True)
class Coverage:
    """Deterministic verification-coverage metrics (never a truth probability)."""

    claims_checked: int = 0
    claims_with_evidence: int = 0
    claims_with_independent_corroboration: int = 0
    claims_with_contradictions: int = 0
    claims_with_unresolved_issues: int = 0


@serializable
@dataclasses.dataclass(frozen=True)
class EvidenceAssessment:
    """The output of assessing evidence against a claim."""

    assessment_id: EvidenceAssessmentId
    claim_id: ClaimId
    evidence_id: EvidenceId
    support_type: SupportType
    rationale: str
    status: VerificationStatus
    quality: EvidenceQuality
    created_at: datetime

    @classmethod
    def create(
        cls,
        claim_id: ClaimId,
        evidence_id: EvidenceId,
        support_type: SupportType,
        rationale: str,
        status: VerificationStatus,
        quality: EvidenceQuality,
    ) -> EvidenceAssessment:
        return cls(
            assessment_id=EvidenceAssessmentId(new_id("assessment")),
            claim_id=claim_id,
            evidence_id=evidence_id,
            support_type=support_type,
            rationale=rationale,
            status=status,
            quality=quality,
            created_at=utc_now(),
        )


@serializable
@dataclasses.dataclass(frozen=True)
class VerificationReport:
    """A structured verification report for a scoped verification run."""

    report_id: VerificationReportId
    scope: VerificationScope
    claim_id: ClaimId | None
    project_id: str
    status: VerificationStatus
    issues: tuple[VerificationIssue, ...]
    evidence: tuple[str, ...]
    contradictions: tuple[str, ...]
    source_assessments: tuple[str, ...]
    coverage: Coverage
    generated_at: datetime

    @classmethod
    def create(
        cls,
        scope: VerificationScope,
        project_id: str,
        status: VerificationStatus,
        *,
        claim_id: ClaimId | None = None,
        issues: tuple[VerificationIssue, ...] = (),
        evidence: tuple[str, ...] = (),
        contradictions: tuple[str, ...] = (),
        source_assessments: tuple[str, ...] = (),
        coverage: Coverage | None = None,
    ) -> VerificationReport:
        return cls(
            report_id=VerificationReportId(new_id("report")),
            scope=scope,
            claim_id=claim_id,
            project_id=project_id,
            status=status,
            issues=issues,
            evidence=evidence,
            contradictions=contradictions,
            source_assessments=source_assessments,
            coverage=coverage or Coverage(),
            generated_at=utc_now(),
        )


@serializable
@dataclasses.dataclass(frozen=True)
class VerificationSummary:
    """A bounded, context-safe summary of a claim's verification outcome.

    Carried inside ``ResearchContext`` so the model sees *how* prior claims were
    verified (scoped status, corroboration, contradiction/issue counts) without
    the full issue list. It is never a truth assertion.
    """

    claim_id: str
    project_id: str
    status: VerificationStatus
    independent_corroboration: bool
    contradiction_count: int
    unresolved_issue_count: int

    @classmethod
    def from_report(cls, report: VerificationReport) -> VerificationSummary:
        return cls(
            claim_id=report.claim_id or "",
            project_id=report.project_id,
            status=report.status,
            independent_corroboration=bool(
                report.coverage.claims_with_independent_corroboration
            ),
            contradiction_count=len(report.contradictions),
            unresolved_issue_count=report.coverage.claims_with_unresolved_issues,
        )


@runtime_checkable
class VerificationAssistant(Protocol):
    """A future model-assisted verification boundary.

    Phase 5 provides only a deterministic no-op implementation; no model is
    called. Future phases may plug a model assistant behind this interface.
    """

    def assess_evidence(self, claim_text: str, evidence_text: str) -> SupportType: ...

    def assess_contradiction(self, claim_a: str, claim_b: str) -> str: ...

    def classify_claim(self, claim_text: str) -> str: ...


class NoOpVerificationAssistant:
    """Deterministic no-op assistant (Phase 5 default)."""

    def assess_evidence(self, claim_text: str, evidence_text: str) -> SupportType:
        return SupportType.UNKNOWN

    def assess_contradiction(self, claim_a: str, claim_b: str) -> str:
        return "insufficient_information"

    def classify_claim(self, claim_text: str) -> str:
        return "unknown"
