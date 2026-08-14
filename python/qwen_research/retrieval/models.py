"""Retrieval and index data models.

Pure dataclasses with no internal imports (a leaf "types" module) so both the
indexing and retrieval layers can depend on them without cycles.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum


class RetrievalMode(StrEnum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclasses.dataclass(frozen=True)
class RetrievedChunk:
    """A ranked search hit with full provenance.

    ``score`` is the *final* relevance used for ranking; the individual score
    components (``lexical_score``, ``semantic_score``, ``fusion_score``,
    ``rerank_score``) are recorded separately and are ``None`` when a retrieval
    stage did not contribute. Retrieval scores are **not** factual confidence,
    source quality, or claim confidence.
    """

    chunk_id: str
    document_id: str
    source_id: str
    text: str
    score: float
    page: int | None = None
    section: str | None = None
    path: str | None = None
    root_id: str | None = None
    relative_path: str | None = None
    media_type: str | None = None
    modified_at: datetime | None = None
    lexical_score: float | None = None
    semantic_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    retrieval_mode: str | None = None
    rank: int | None = None


@dataclasses.dataclass(frozen=True)
class SearchFilters:
    """Optional filters for a search."""

    roots: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    path_prefix: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclasses.dataclass(frozen=True)
class SearchOptions:
    """Search options.

    ``mode`` selects the retrieval strategy; the candidate counts
    (``lexical_k``/``semantic_k``/``final_k``) and ``max_chunks_per_document``
    tune hybrid retrieval and diversity. Existing filters are preserved.
    """

    limit: int = 10
    roots: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    path_prefix: str | None = None
    date_range: tuple[datetime, datetime] | None = None
    minimum_score: float | None = None
    mode: RetrievalMode = RetrievalMode.HYBRID
    lexical_k: int = 20
    semantic_k: int = 20
    final_k: int = 10
    max_chunks_per_document: int = 3
    #: Recall safeguard for semantic retrieval when the backend has no native
    #: metadata filtering: the vector index is asked for ``candidate_limit``
    #: chunks, filters are applied, then the final ``limit`` is returned.
    semantic_overfetch_factor: int = 5
    minimum_candidate_pool: int = 20

    def semantic_candidate_limit(self) -> int:
        """The number of semantic candidates to fetch before filtering.

        Distinct from the final ``limit``: overfetch preserves recall when the
        top semantic candidates fall outside the requested filters. This is a
        recall safeguard, never a confidence measure.
        """
        return max(
            self.limit * self.semantic_overfetch_factor,
            self.minimum_candidate_pool,
        )


@dataclasses.dataclass(frozen=True)
class RetrievalQuery:
    """A normalized retrieval request.

    Wraps the raw query, its normalized form, filters, mode, and candidate
    limits. Used by the hybrid retriever; derived from ``SearchOptions`` so no
    duplicate filter representation exists.
    """

    raw: str
    normalized: str
    mode: RetrievalMode
    lexical_k: int
    semantic_k: int
    final_k: int
    max_chunks_per_document: int
    filters: SearchFilters

    @classmethod
    def from_options(cls, query: str, options: SearchOptions) -> RetrievalQuery:
        return cls(
            raw=query,
            normalized=query.strip().lower(),
            mode=options.mode,
            lexical_k=max(1, options.lexical_k),
            semantic_k=max(1, options.semantic_k),
            final_k=max(1, options.final_k),
            max_chunks_per_document=max(1, options.max_chunks_per_document),
            filters=SearchFilters(
                roots=options.roots,
                document_types=options.document_types,
                path_prefix=options.path_prefix,
            ),
        )


@dataclasses.dataclass(frozen=True)
class SearchResult:
    """A retrieval result: ranked chunks plus diagnostics.

    The optional metric fields record candidate provenance (lexical vs semantic
    hits and their intersection) for internal evaluation; they are ``None`` for
    single-mode retrievers.
    """

    chunks: tuple[RetrievedChunk, ...]
    query: str
    candidate_count: int
    returned_count: int
    duration_ms: float
    mode: str | None = None
    lexical_hits: int | None = None
    semantic_hits: int | None = None
    intersection_count: int | None = None
    #: Degradation metadata: set when a backend fell back. ``degraded`` is
    #: False on a normal (non-fallback) result; ``degradation_reason`` is a
    #: short, stable identifier (not free-form prose).
    degraded: bool = False
    degradation_reason: str | None = None
    semantic_available: bool | None = None
    lexical_available: bool | None = None


@dataclasses.dataclass(frozen=True)
class DocumentView:
    """A document's metadata and structure (for ``get_source``)."""

    document_id: str
    source_id: str
    root_id: str
    relative_path: str
    display_path: str
    media_type: str
    title: str
    metadata: dict[str, str]
    content_hash: str
    size_bytes: int
    modified_at: datetime | None
    sections: tuple[tuple[int | None, str | None], ...]  # (page, heading)


@dataclasses.dataclass(frozen=True)
class CorpusStats:
    """Aggregate index statistics."""

    roots: int
    documents: int
    chunks: int
    indexed_bytes: int
    last_index_time: datetime | None
    failures: int
    stale_documents: int


class IndexState(StrEnum):
    NOT_INITIALIZED = "not_initialized"
    READY = "ready"
    INDEXING = "indexing"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class IndexStatus:
    """Diagnostic index status."""

    state: IndexState
    last_scan: datetime | None
    last_success: datetime | None
    documents: int
    chunks: int
    failures: int
    stale: int
