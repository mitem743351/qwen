"""Markdown parser.

Strips the most common Markdown block markers for a cleaner searchable text
while preserving heading structure as sections for citation. Content is
normalized; the raw file is never modified.
"""

from __future__ import annotations

import re

from qwen_research.corpus.records import DocumentSection, FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.documents.text import read_text

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_FENCE_RE = re.compile(r"^```.*?^```\s*$", re.DOTALL | re.MULTILINE)
_CODE_INLINE_RE = re.compile(r"`([^`]*)`")


class MarkdownParser:
    """Parses Markdown files (``text/markdown``) into normalized text."""

    media_types: tuple[str, ...] = ("text/markdown",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        raw = read_text(file_record.path)
        sections: list[DocumentSection] = []
        for i, match in enumerate(_HEADING_RE.finditer(raw)):
            sections.append(
                DocumentSection(
                    section_id=f"{file_record.relative_path}#s{i}",
                    document_id="",  # assigned by the index
                    page=None,
                    heading=match.group(2).strip(),
                    start_offset=match.start(),
                    end_offset=match.end(),
                )
            )
        # Strip fenced code blocks' fences but keep their content.
        text = _FENCE_RE.sub(lambda m: m.group(0)[3:-3], raw)
        text = _HEADING_RE.sub(lambda m: m.group(2), text)
        text = _CODE_INLINE_RE.sub(r"\1", text)
        return ParsedDocument(
            text=normalize_text(text),
            sections=tuple(sections),
            status=ParseStatus.OK,
        )
