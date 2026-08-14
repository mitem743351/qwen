"""Retrieval and index data models.

Pure dataclasses with no internal imports (a leaf "types" module) so both the
indexing and retrieval layers can depend on them without cycles.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum


@dataclasses.dataclass(frozen=True)
class RetrievedChunk:
    """A ranked search hit with full provenance.

    ``score`` is the search-method relevance (e.g. FTS bm25); it is **not**
    factual confidence.
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
    """Search options."""

    limit: int = 10
    roots: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    path_prefix: str | None = None
    date_range: tuple[datetime, datetime] | None = None
    minimum_score: float | None = None


@dataclasses.dataclass(frozen=True)
class SearchResult:
    """A retrieval result: ranked chunks plus diagnostics."""

    chunks: tuple[RetrievedChunk, ...]
    query: str
    candidate_count: int
    returned_count: int
    duration_ms: float


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
