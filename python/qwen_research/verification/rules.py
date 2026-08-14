"""Deterministic verification rules.

Each rule inspects a claim together with its linked evidence, source-quality
assessments, and corpus facts, and returns a list of :class:`VerificationIssue`.
Rules are pure and deterministic; they never invoke a model.
"""

from __future__ import annotations

import dataclasses

from qwen_research.claims.models import Claim
from qwen_research.claims.relationships import ClaimEvidenceLink, ClaimEvidenceRelationship
from qwen_research.evidence.models import EvidenceRecord, ExtractionQuality
from qwen_research.sources.quality import SourceQuality
from qwen_research.verification.models import Severity, VerificationIssue


@dataclasses.dataclass(frozen=True)
class VerificationFacts:
    """Facts assembled by the engine before running rules."""

    claim: Claim
    evidence: dict[str, EvidenceRecord]
    links: list[ClaimEvidenceLink]
    source_quality: dict[str, SourceQuality]
    chunk_status: dict[str, str]  # evidence_id -> "valid" | "missing" | "stale"
    independent_source_count: int
    same_source_evidence_count: int


def _issue(
    code: str, severity: Severity, entity_type: str, entity_id: str, message: str
) -> VerificationIssue:
    return VerificationIssue(code, severity, entity_type, entity_id, message)


def rule_claim_has_no_evidence(facts: VerificationFacts) -> list[VerificationIssue]:
    if not facts.evidence and not facts.links:
        return [
            _issue(
                "claim_has_no_evidence",
                Severity.WARNING,
                "claim",
                facts.claim.claim_id,
                "claim has no linked evidence",
            )
        ]
    return []


def rule_evidence_source_missing(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for eid, evidence in facts.evidence.items():
        if evidence.source_id not in facts.source_quality:
            out.append(
                _issue(
                    "evidence_source_missing",
                    Severity.ERROR,
                    "evidence",
                    eid,
                    f"evidence source {evidence.source_id!r} not found in corpus",
                )
            )
    return out


def rule_evidence_chunk_missing(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for eid, status in facts.chunk_status.items():
        if status == "missing":
            out.append(
                _issue(
                    "evidence_chunk_missing",
                    Severity.ERROR,
                    "evidence",
                    eid,
                    "evidence chunk no longer present in the index",
                )
            )
    return out


def rule_evidence_excerpt_empty(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for eid, evidence in facts.evidence.items():
        if not evidence.excerpt.strip():
            out.append(
                _issue(
                    "evidence_excerpt_empty",
                    Severity.ERROR,
                    "evidence",
                    eid,
                    "evidence excerpt is empty",
                )
            )
    return out


def rule_source_provenance_incomplete(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for source_id, quality in facts.source_quality.items():
        if quality.provenance_completeness != "complete":
            out.append(
                _issue(
                    "source_provenance_incomplete",
                    Severity.WARNING,
                    "source",
                    source_id,
                    "source provenance is incomplete",
                )
            )
    return out


def rule_duplicate_evidence(facts: VerificationFacts) -> list[VerificationIssue]:
    seen: set[str] = set()
    out = []
    for link in facts.links:
        if link.evidence_id in seen:
            out.append(
                _issue(
                    "duplicate_evidence",
                    Severity.INFO,
                    "evidence",
                    link.evidence_id,
                    "duplicate evidence link for the same claim",
                )
            )
        seen.add(link.evidence_id)
    return out


def rule_no_independent_corroboration(facts: VerificationFacts) -> list[VerificationIssue]:
    if facts.evidence and facts.independent_source_count < 2:
        return [
            _issue(
                "no_independent_corroboration",
                Severity.INFO,
                "claim",
                facts.claim.claim_id,
                "claim lacks independent corroboration (single source)",
            )
        ]
    return []


def rule_support_contradiction_conflict(facts: VerificationFacts) -> list[VerificationIssue]:
    has_support = any(
        link.relationship is ClaimEvidenceRelationship.SUPPORTS for link in facts.links
    )
    has_contradiction = any(
        link.relationship is ClaimEvidenceRelationship.CONTRADICTS for link in facts.links
    )
    if has_support and has_contradiction:
        return [
            _issue(
                "support_contradiction_conflict",
                Severity.ERROR,
                "claim",
                facts.claim.claim_id,
                "claim has both supporting and contradicting evidence",
            )
        ]
    return []


def rule_stale_document(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for eid, status in facts.chunk_status.items():
        if status == "stale":
            out.append(
                _issue(
                    "stale_document",
                    Severity.ERROR,
                    "evidence",
                    eid,
                    "evidence comes from a stale document",
                )
            )
    return out


def rule_unextractable_source(facts: VerificationFacts) -> list[VerificationIssue]:
    out = []
    for eid, evidence in facts.evidence.items():
        quality = facts.source_quality.get(evidence.source_id)
        if quality is not None and quality.extraction_quality in (
            ExtractionQuality.UNEXTRACTABLE.value,
            ExtractionQuality.OCR_REQUIRED.value,
        ):
            out.append(
                _issue(
                    "unextractable_source",
                    Severity.WARNING,
                    "evidence",
                    eid,
                    f"source extraction quality is {quality.extraction_quality}",
                )
            )
    return out


ALL_RULES = (
    rule_claim_has_no_evidence,
    rule_evidence_source_missing,
    rule_evidence_chunk_missing,
    rule_evidence_excerpt_empty,
    rule_source_provenance_incomplete,
    rule_duplicate_evidence,
    rule_no_independent_corroboration,
    rule_support_contradiction_conflict,
    rule_stale_document,
    rule_unextractable_source,
)


def run_rules(facts: VerificationFacts) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    for rule in ALL_RULES:
        issues.extend(rule(facts))
    return issues
