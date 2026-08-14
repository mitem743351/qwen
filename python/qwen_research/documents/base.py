"""Document parser protocol and registry.

A parser converts a :class:`~qwen_research.corpus.records.FileRecord` into a
:class:`ParsedDocument` (normalized text + structure). Parsers are registered
against media types so new document types are pluggable without touching the
pipeline.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable

from qwen_research.corpus.records import DocumentSection, FileRecord, ParseStatus


@dataclasses.dataclass(frozen=True)
class ParsedDocument:
    """Normalized extracted content for one document.

    ``document_id`` is assigned by the index (parser-independent). ``status`` is
    ``OK`` on success, ``UNEXTRACTABLE`` when a file (e.g. a scanned PDF) has no
    extractable text, and ``ERROR`` for parse failures that must be recorded.
    """

    text: str
    sections: tuple[DocumentSection, ...] = ()
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)
    status: ParseStatus = ParseStatus.OK


@runtime_checkable
class DocumentParser(Protocol):
    """A pluggable document parser."""

    media_types: tuple[str, ...]

    def supports(self, media_type: str) -> bool: ...

    def parse(self, file_record: FileRecord) -> ParsedDocument: ...


_PARSERS: dict[str, DocumentParser] = {}


def register_parser(parser: DocumentParser) -> None:
    """Register *parser* for each of its declared media types."""
    for media_type in parser.media_types:
        _PARSERS[media_type] = parser


def parser_for(media_type: str) -> DocumentParser | None:
    return _PARSERS.get(media_type)
