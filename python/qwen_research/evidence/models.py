"""Evidence model.

Evidence is the evaluated unit between a retrieved chunk and a claim. An
``EvidenceRecord`` carries full provenance (source/document/chunk), an
evaluative support type (never derived from retrieval score), extraction
quality (consumed from Phase 3 parser metadata), and an independent quality
breakdown. The lightweight domain ``Evidence`` object remains the in-memory
evidence reference; this record is the persistent, claim-relationship-bearing
extension.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import EvidenceId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.sources.quality import SourceQuality


class SupportType(StrEnum):
    """The evaluative relationship between an evidence item and a claim.

    Determined by assessment, **never** by retrieval relevance.
    """

    DIRECT_SUPPORT = "direct_support"
    INDIRECT_SUPPORT = "indirect_support"
    CONTEXT = "context"
    QUALIFICATION = "qualification"
    CONTRADICTION = "contradiction"
    NON_SUPPORT = "non_support"
    UNKNOWN = "unknown"


class ExtractionQuality(StrEnum):
    """Whether the evidence text was extracted cleanly (from Phase 3 parsers)."""

    CLEAN = "clean"
    PARTIAL = "partial"
    OCR_REQUIRED = "ocr_required"
    PARSER_DEGRADED = "parser_degraded"
    UNEXTRACTABLE = "unextractable"
    UNKNOWN = "unknown"


@serializable
@dataclasses.dataclass(frozen=True)
class EvidenceQuality:
    """A structured, multi-dimensional evidence evaluation.

    Individual dimensions are kept separate; no single confidence score is
    fabricated.
    """

    source_quality: SourceQuality | None = None
    extraction_quality: ExtractionQuality = ExtractionQuality.UNKNOWN
    relevance: float | None = None
    directness: str | None = None
    corroboration: int = 0
    contradiction: int = 0


@serializable
@dataclasses.dataclass(frozen=True)
class EvidenceRecord:
    """A first-class evidence record with full provenance and evaluation state."""

    evidence_id: EvidenceId
    source_id: str
    document_id: str | None
    chunk_id: str | None
    claim_refs: tuple[str, ...]
    excerpt: str
    location: str
    relevance: float | None
    support_type: SupportType
    extraction_method: str
    source_quality: SourceQuality | None
    verification_status: str
    provenance: dict[str, str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        source_id: str,
        excerpt: str,
        *,
        document_id: str | None = None,
        chunk_id: str | None = None,
        location: str = "",
        relevance: float | None = None,
        support_type: SupportType = SupportType.UNKNOWN,
        extraction_method: str = "explicit",
        source_quality: SourceQuality | None = None,
        verification_status: str = "unreviewed",
        provenance: dict[str, str] | None = None,
    ) -> EvidenceRecord:
        now = utc_now()
        return cls(
            evidence_id=EvidenceId(new_id("evidence")),
            source_id=source_id,
            document_id=document_id,
            chunk_id=chunk_id,
            claim_refs=(),
            excerpt=excerpt,
            location=location,
            relevance=relevance,
            support_type=support_type,
            extraction_method=extraction_method,
            source_quality=source_quality,
            verification_status=verification_status,
            provenance=dict(provenance or {}),
            created_at=now,
            updated_at=now,
        )
