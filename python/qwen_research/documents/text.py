"""Plain-text parser and shared decoding helpers."""

from __future__ import annotations

from pathlib import Path

from qwen_research.corpus.records import FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.domain.errors import DocumentParseError


def read_text(path: str) -> str:
    """Read a file as UTF-8 (with BOM), raising on undecodable content.

    We deliberately do **not** silently fall back to a lossy codec: undecodable
    content is recorded as a parse error rather than corrupted.
    """
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("file is not valid UTF-8")


class PlainTextParser:
    """Parses plain-text files (``text/plain``)."""

    media_types: tuple[str, ...] = ("text/plain",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        text = normalize_text(read_text(file_record.path))
        return ParsedDocument(text=text, status=ParseStatus.OK)
