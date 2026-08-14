"""The deterministic VerificationEngine.

Coordinates provenance, source-quality, evidence, claim-evidence,
corroboration, and contradiction checks into a single scoped
:class:`VerificationReport`. It makes no unsupported truth claims: statuses are
scoped to "within the currently indexed corpus".
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.claims.models import Claim
from qwen_research.claims.relationships import ClaimEvidenceLink, ClaimEvidenceRelationship
from qwen_research.common.ids import EvidenceId
from qwen_research.common.timestamps import utc_now
from qwen_research.contradictions.models import Contradiction, ContradictionStatus
from qwen_research.corpus.records import Document
from qwen_research.evidence.models import EvidenceRecord, ExtractionQuality, SupportType
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import RetrievedChunk
from qwen_research.sources.quality import SourceQuality, SourceQualityAssessor
from qwen_research.verification.models import (
    Coverage,
    NoOpVerificationAssistant,
    Severity,
    VerificationAssistant,
    VerificationIssue,
    VerificationReport,
    VerificationScope,
    VerificationStatus,
)
from qwen_research.verification.repositories import VerificationStore
from qwen_research.verification.rules import VerificationFacts, run_rules


@runtime_checkable
class EvidenceSource(Protocol):
    """A source of chunk metadata for materializing evidence."""

    def get_chunks_for_ids(self, chunk_ids: list[str]) -> list[RetrievedChunk]: ...
    def list_documents(self) -> list[Document]: ...
    def get_document(self, document_id: str) -> object | None: ...


def _support_type_for(link: ClaimEvidenceLink) -> SupportType:
    return {
        ClaimEvidenceRelationship.SUPPORTS: SupportType.DIRECT_SUPPORT,
        ClaimEvidenceRelationship.CONTRADICTS: SupportType.CONTRADICTION,
        ClaimEvidenceRelationship.QUALIFIES: SupportType.QUALIFICATION,
        ClaimEvidenceRelationship.CONTEXTUALIZES: SupportType.CONTEXT,
        ClaimEvidenceRelationship.DOES_NOT_ADDRESS: SupportType.NON_SUPPORT,
    }.get(link.relationship, SupportType.UNKNOWN)


class VerificationEngine:
    """Provider-independent deterministic verification pipeline."""

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
        self._assessor = assessor or SourceQualityAssessor()
        self._assistant = assistant or NoOpVerificationAssistant()

    # -- fact assembly -----------------------------------------------------

    def _documents(self) -> dict[str, dict]:
        if self._corpus is None:
            return {}
        return {d.source_id: _document_as_dict(d) for d in self._corpus.list_documents()}

    def _chunks(self, chunk_ids: list[str]) -> dict[str, RetrievedChunk]:
        if self._corpus is None:
            return {}
        chunks = self._corpus.get_chunks_for_ids(list(chunk_ids))
        return {c.chunk_id: c for c in chunks}

    def _stale_document_ids(self) -> set[str]:
        if self._corpus is None:
            return set()
        stale_fn = getattr(self._corpus, "list_stale_document_ids", None)
        if stale_fn is None:
            return set()
        return set(stale_fn())

    def _source_quality(self, source_id: str, docs: dict[str, dict]) -> SourceQuality:
        cached = self._store.get_source_quality(source_id)
        if cached is not None:
            return cached
        doc = docs.get(source_id, {})
        metadata = dict(doc.get("metadata", {}))
        if doc.get("content_hash"):
            metadata["content_hash"] = doc["content_hash"]
        quality = self._assessor.assess(
            media_type=doc.get("media_type", ""),
            metadata=metadata,
        )
        self._store.save_source_quality(source_id, quality)
        return quality

    def materialize_evidence(self, chunk: RetrievedChunk) -> EvidenceRecord:
        """Build an :class:`EvidenceRecord` from a retrieved chunk."""
        docs = self._documents()
        doc = docs.get(chunk.source_id, {})
        quality = self._source_quality(chunk.source_id, docs)
        parse_status = doc.get("metadata", {}).get("parse_status", "ok")
        extraction = (
            ExtractionQuality.UNEXTRACTABLE.value
            if parse_status == "unextractable"
            else (
                ExtractionQuality.CLEAN.value
                if parse_status == "ok"
                else ExtractionQuality.PARSER_DEGRADED.value
            )
        )
        now = utc_now()
        return EvidenceRecord(
            evidence_id=EvidenceId(chunk.chunk_id),
            source_id=chunk.source_id,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            claim_refs=(),
            excerpt=chunk.text,
            location=chunk.relative_path or chunk.path or "",
            relevance=chunk.score,
            support_type=SupportType.UNKNOWN,
            extraction_method="retrieval",
            source_quality=quality,
            verification_status=VerificationStatus.RETRIEVED.value,
            provenance={
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "parse_status": parse_status,
                "extraction_quality": extraction,
            },
            created_at=now,
            updated_at=now,
        )

    # -- verification ------------------------------------------------------

    def verify_claim(
        self,
        claim: Claim,
        *,
        links: list[ClaimEvidenceLink] | None = None,
        contradictions: list[Contradiction] | None = None,
    ) -> VerificationReport:
        """Run the deterministic pipeline for a single claim."""
        links = links if links is not None else self._store.get_links(claim.claim_id)
        contradictions = contradictions if contradictions is not None else []

        evidence_ids: list[str] = [str(link.evidence_id) for link in links]
        chunks = self._chunks(evidence_ids)
        docs = self._documents()

        stale_ids = self._stale_document_ids()
        evidence: dict[str, EvidenceRecord] = {}
        chunk_status: dict[str, str] = {}
        source_quality: dict[str, SourceQuality] = {}
        for eid in evidence_ids:
            chunk = chunks.get(eid)
            if chunk is None:
                chunk_status[eid] = "missing"
                continue
            chunk_status[eid] = "stale" if chunk.document_id in stale_ids else "valid"
            record = self.materialize_evidence(chunk)
            evidence[eid] = record
            source_quality[record.source_id] = self._source_quality(record.source_id, docs)

        supporting = [
            link for link in links
            if link.relationship is ClaimEvidenceRelationship.SUPPORTS
        ]
        independence_units = {
            evidence[link.evidence_id].document_id or evidence[link.evidence_id].source_id
            for link in supporting
            if link.evidence_id in evidence
        }
        independent_source_count = len(independence_units)
        same_source_evidence_count = max(0, len(supporting) - independent_source_count)

        facts = VerificationFacts(
            claim=claim,
            evidence=evidence,
            links=links,
            source_quality=source_quality,
            chunk_status=chunk_status,
            independent_source_count=independent_source_count,
            same_source_evidence_count=same_source_evidence_count,
        )
        issues = run_rules(facts)

        status = _derive_status(links, contradictions, issues, independent_source_count)
        coverage = Coverage(
            claims_checked=1,
            claims_with_evidence=1 if evidence else 0,
            claims_with_independent_corroboration=1 if independent_source_count >= 2 else 0,
            claims_with_contradictions=1 if any(
                c.status is ContradictionStatus.CONFIRMED for c in contradictions
            ) else 0,
            claims_with_unresolved_issues=1 if any(
                i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues
            ) else 0,
        )

        return VerificationReport.create(
            scope=VerificationScope.CLAIM,
            project_id=claim.project_id,
            status=status,
            claim_id=claim.claim_id,
            issues=tuple(issues),
            evidence=tuple(sorted(evidence)),
            contradictions=tuple(sorted(c.contradiction_id for c in contradictions)),
            source_assessments=tuple(sorted(source_quality)),
            coverage=coverage,
        )


def _derive_status(
    links: list[ClaimEvidenceLink],
    contradictions: list[Contradiction],
    issues: list[VerificationIssue],
    independent_source_count: int,
) -> VerificationStatus:
    if not links:
        return VerificationStatus.INSUFFICIENT_EVIDENCE
    if any(c.status is ContradictionStatus.CONFIRMED for c in contradictions):
        return VerificationStatus.CONTRADICTED
    if any(link.relationship is ClaimEvidenceRelationship.CONTRADICTS for link in links):
        return VerificationStatus.CONTESTED
    has_support = any(link.relationship is ClaimEvidenceRelationship.SUPPORTS for link in links)
    if not has_support:
        return VerificationStatus.ASSESSED
    has_error = any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues)
    if independent_source_count >= 2 and not has_error:
        return VerificationStatus.VERIFIED_WITHIN_CORPUS
    if has_error:
        return VerificationStatus.PARTIALLY_SUPPORTED
    return VerificationStatus.SUPPORTED


def _document_as_dict(doc: Document) -> dict:
    return {
        "source_id": doc.source_id,
        "document_id": doc.document_id,
        "media_type": doc.media_type,
        "metadata": dict(doc.metadata),
        "content_hash": doc.content_hash,
        "modified_at": doc.modified_at,
        "relative_path": doc.relative_path,
    }
