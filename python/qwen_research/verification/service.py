"""Evidence-integrity application service.

The provider-independent façade used by the Research Runtime. It owns claim
creation, claim–evidence linking, evidence assessment, verification, and
contradiction access. All writes are transactional and provenance-validated;
``UNREVIEWED`` claims are never silently promoted.
"""

from __future__ import annotations

from qwen_research.claims.models import Claim, ClaimStatus, ClaimType, QuantitativeClaim, Scope
from qwen_research.claims.relationships import ClaimEvidenceLink, ClaimEvidenceRelationship
from qwen_research.common.ids import ClaimId, EvidenceId
from qwen_research.contradictions.detector import detect_contradictions
from qwen_research.contradictions.models import Contradiction
from qwen_research.domain.errors import ClaimNotFoundError, EvidenceNotFoundError
from qwen_research.evidence.models import (
    EvidenceQuality,
    EvidenceRecord,
    ExtractionQuality,
    SupportType,
)
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.sources.quality import SourceQualityAssessor
from qwen_research.verification.engine import VerificationEngine, _support_type_for
from qwen_research.verification.models import (
    EvidenceAssessment,
    NoOpVerificationAssistant,
    VerificationAssistant,
    VerificationReport,
    VerificationStatus,
)
from qwen_research.verification.repositories import VerificationStore


class EvidenceIntegrityService:
    """Application-level evidence integrity and verification operations."""

    def __init__(
        self,
        store: VerificationStore,
        *,
        corpus_index: CorpusIndex | None = None,
        assessor: SourceQualityAssessor | None = None,
        assistant: VerificationAssistant | None = None,
    ) -> None:
        self._store = store
        self._corpus = corpus_index
        self._engine = VerificationEngine(
            store,
            corpus_index=corpus_index,
            assessor=assessor,
            assistant=assistant or NoOpVerificationAssistant(),
        )

    def initialize(self) -> None:
        self._store.initialize()

    # -- claims ------------------------------------------------------------

    def create_claim(
        self,
        project_id: str,
        text: str,
        *,
        claim_type: ClaimType = ClaimType.UNKNOWN,
        source_refs: tuple[str, ...] = (),
        scope: Scope | None = None,
        quantitative: QuantitativeClaim | None = None,
    ) -> Claim:
        """Create a structured claim in the ``UNREVIEWED`` state."""
        claim = Claim.create(
            project_id,
            text,
            claim_type=claim_type,
            source_refs=source_refs,
            scope=scope,
            quantitative=quantitative,
        )
        self._store.save_claim(claim)
        return claim

    def get_claim(self, claim_id: str) -> Claim:
        claim = self._store.get_claim(claim_id)
        if claim is None:
            raise ClaimNotFoundError(f"claim {claim_id!r} not found")
        return claim

    # -- linking -----------------------------------------------------------

    def link_claim_evidence(
        self,
        claim_id: str,
        evidence_id: str,
        relationship: ClaimEvidenceRelationship,
        rationale: str = "",
    ) -> ClaimEvidenceLink:
        """Link a claim to evidence with an explicit relationship.

        Validates the claim and evidence exist before writing (atomic).
        """
        self.get_claim(claim_id)
        if not self._evidence_exists(evidence_id):
            raise EvidenceNotFoundError(f"evidence {evidence_id!r} not found in corpus")
        link = ClaimEvidenceLink.create(
            ClaimId(claim_id), EvidenceId(evidence_id), relationship, rationale
        )
        self._store.save_link(link)
        return link

    # -- assessment --------------------------------------------------------

    def assess_evidence(self, claim_id: str, evidence_id: str) -> EvidenceAssessment:
        """Produce a structured assessment of evidence against a claim."""
        self.get_claim(claim_id)
        record = self._materialize(evidence_id)
        if record is None:
            raise EvidenceNotFoundError(f"evidence {evidence_id!r} not found in corpus")

        links = self._store.get_links(claim_id)
        link = next((x for x in links if x.evidence_id == evidence_id), None)
        support_type = _support_type_for(link) if link is not None else SupportType.UNKNOWN

        quality = EvidenceQuality(
            source_quality=record.source_quality,
            extraction_quality=_extraction_quality(record),
            relevance=record.relevance,
            directness=(
                "direct" if support_type is SupportType.DIRECT_SUPPORT else None
            ),
            corroboration=0,
            contradiction=0,
        )
        assessment = EvidenceAssessment.create(
            claim_id=ClaimId(claim_id),
            evidence_id=EvidenceId(evidence_id),
            support_type=support_type,
            rationale=link.rationale if link is not None else "",
            status=VerificationStatus.ASSESSED,
            quality=quality,
        )
        self._store.save_assessment(assessment)
        return assessment

    # -- verification ------------------------------------------------------

    def verify_claim(self, claim_id: str) -> VerificationReport:
        """Run the deterministic verification pipeline and persist the report."""
        claim = self.get_claim(claim_id)
        self._detect_project_contradictions(claim.project_id)
        links = self._store.get_links(claim_id)
        contradictions = self._store.get_contradictions_for_claim(claim_id)
        report = self._engine.verify_claim(
            claim, links=links, contradictions=contradictions
        )
        self._store.save_report(report)
        self._update_claim_status(claim, report.status)
        return report

    def get_verification_report(self, report_id: str) -> VerificationReport:
        report = self._store.get_report(report_id)
        if report is None:
            from qwen_research.domain.errors import VerificationReportNotFoundError

            raise VerificationReportNotFoundError(f"report {report_id!r} not found")
        return report

    def get_contradictions(self, project_id: str) -> list[Contradiction]:
        """Return contradiction candidates/confirmations for a project scope."""
        self._detect_project_contradictions(project_id)
        return self._store.get_contradictions(project_id)

    # -- internals ---------------------------------------------------------

    def _evidence_exists(self, evidence_id: str) -> bool:
        if self._corpus is None:
            return False
        return bool(self._corpus.get_chunks_for_ids([evidence_id]))

    def _materialize(self, evidence_id: str) -> EvidenceRecord | None:
        if self._corpus is None:
            return None
        chunks = self._corpus.get_chunks_for_ids([evidence_id])
        if not chunks:
            return None
        return self._engine.materialize_evidence(chunks[0])

    def _detect_project_contradictions(self, project_id: str) -> None:
        claims = self._store.get_claims(project_id)
        existing = self._store.get_contradictions(project_id)
        seen = {_pair_key(c.claim_a, c.claim_b) for c in existing}
        for contradiction in detect_contradictions(claims):
            key = _pair_key(contradiction.claim_a, contradiction.claim_b)
            if key in seen:
                continue
            seen.add(key)
            self._store.save_contradiction(contradiction)

    def _update_claim_status(self, claim: Claim, status: VerificationStatus) -> None:
        self._store.update_claim(claim.with_status(_claim_status_for(status)))


def _pair_key(a: str, b: str) -> tuple[str, str]:
    ordered = sorted((a, b))
    return (ordered[0], ordered[1])


def _extraction_quality(record: EvidenceRecord) -> ExtractionQuality:
    if record.source_quality is None:
        return ExtractionQuality.UNKNOWN
    try:
        return ExtractionQuality(record.source_quality.extraction_quality)
    except ValueError:
        return ExtractionQuality.UNKNOWN


def _claim_status_for(status: VerificationStatus) -> ClaimStatus:
    return {
        VerificationStatus.VERIFIED_WITHIN_CORPUS: ClaimStatus.CORROBORATED,
        VerificationStatus.SUPPORTED: ClaimStatus.SUPPORTED,
        VerificationStatus.PARTIALLY_SUPPORTED: ClaimStatus.SUPPORTED,
        VerificationStatus.CONTESTED: ClaimStatus.CONTESTED,
        VerificationStatus.CONTRADICTED: ClaimStatus.CONTESTED,
        VerificationStatus.ASSESSED: ClaimStatus.ASSESSED,
        VerificationStatus.INSUFFICIENT_EVIDENCE: ClaimStatus.UNREVIEWED,
        VerificationStatus.RETRIEVED: ClaimStatus.UNREVIEWED,
        VerificationStatus.UNREVIEWED: ClaimStatus.UNREVIEWED,
    }[status]
