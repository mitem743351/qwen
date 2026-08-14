"""Corpus index interface.

The retrieval subsystem depends on this interface, never on SQL statements.
The SQLite implementation lives in :mod:`qwen_research.indexing.sqlite`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from qwen_research.corpus.records import Chunk, Document, DocumentContent, DocumentSection
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    RetrievedChunk,
    SearchFilters,
)


@runtime_checkable
class CorpusIndex(Protocol):
    """Storage abstraction for the searchable corpus index."""

    def initialize(self) -> None:
        """Create/verify the schema (idempotent)."""
        ...

    def upsert_roots(
        self, roots: Iterable[tuple[str, str, str | None, bool, bool]]
    ) -> None:
        """Register configured corpus roots (idempotent)."""
        ...

    def set_metadata(self, key: str, value: str) -> None:
        """Store an index metadata key/value (e.g. last-scan timestamps)."""
        ...

    def upsert_document(
        self,
        document: Document,
        content: DocumentContent,
        chunks: list[Chunk],
        sections: list[DocumentSection],
    ) -> None:
        """Insert or replace a document, its sections, and its chunks."""
        ...

    def mark_missing(self, relative_paths: Iterable[str]) -> int:
        """Mark documents whose files are no longer present as stale."""
        ...

    def remove_document(self, document_id: str) -> None:
        """Remove a document and its chunks from the index."""
        ...

    def remove_stale(self) -> int:
        """Remove all stale documents; return the count removed."""
        ...

    def clear(self) -> None:
        """Drop all documents/chunks (keeps roots and metadata)."""
        ...

    def search(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        """Return ranked chunks for *query*."""
        ...

    def get_document(self, document_id: str) -> DocumentView | None:
        """Return a document view by id, or None."""
        ...

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return a chunk by id, or None."""
        ...

    def list_documents(self) -> list[Document]:
        """Return all indexed document metadata."""
        ...

    def document_hash_map(self) -> dict[str, str]:
        """Return {relative_path: content_hash} for incremental scanning."""
        ...

    def stats(self) -> CorpusStats:
        """Return aggregate index statistics."""
        ...

    def status(self) -> IndexStatus:
        """Return diagnostic index status."""
        ...
