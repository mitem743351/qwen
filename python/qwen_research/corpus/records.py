"""Corpus records: stable intermediate representations.

These are value objects shared by the scanner, document pipeline, and index.
They are transport-neutral and carry no provider or MCP specifics.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum


class FileStatus(StrEnum):
    """Scan status of a file relative to the index."""

    NEW = "new"
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    TOO_LARGE = "too_large"
    ERROR = "error"


class ParseStatus(StrEnum):
    """Outcome of parsing a discovered file."""

    OK = "ok"
    UNEXTRACTABLE = "unextractable"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class FileRecord:
    """A discovered file and its metadata (content is not parsed here)."""

    path: str
    root_id: str
    relative_path: str
    extension: str
    media_type: str
    size_bytes: int
    modified_at: datetime | None
    content_hash: str
    status: FileStatus = FileStatus.NEW


@dataclasses.dataclass(frozen=True)
class Document:
    """Provider-neutral document metadata (raw source metadata only)."""

    document_id: str
    source_id: str
    path: str
    root_id: str
    relative_path: str
    media_type: str
    title: str
    metadata: dict[str, str]
    content_hash: str
    size_bytes: int
    modified_at: datetime | None


@dataclasses.dataclass(frozen=True)
class DocumentSection:
    """A structural section of a document (page/heading span)."""

    section_id: str
    document_id: str
    page: int | None
    heading: str | None
    start_offset: int
    end_offset: int


@dataclasses.dataclass(frozen=True)
class DocumentContent:
    """Extracted, normalized text plus structure.

    ``text`` is the full normalized text; ``sections`` carry page/heading
    boundaries for citation. Content is never stored in the primary metadata
    object (:class:`Document`).
    """

    document_id: str
    text: str
    sections: tuple[DocumentSection, ...] = ()
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Chunk:
    """A searchable text span with full provenance."""

    chunk_id: str
    document_id: str
    source_id: str
    text: str
    page: int | None = None
    section: str | None = None
    start_offset: int = 0
    end_offset: int = 0
