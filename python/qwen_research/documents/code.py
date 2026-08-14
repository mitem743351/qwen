"""Source-code parser.

Code files are treated as text: normalized and indexed verbatim (with comments
retained — they are valuable searchable content). No syntax parsing is done.
"""

from __future__ import annotations

from qwen_research.corpus.records import FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.documents.text import read_text

_CODE_MEDIA_TYPES: tuple[str, ...] = (
    "text/x-python",
    "text/x-rust",
    "text/x-typescript",
    "text/javascript",
    "text/x-sql",
)


class CodeParser:
    """Parses source-code files as normalized text."""

    media_types: tuple[str, ...] = _CODE_MEDIA_TYPES

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        text = normalize_text(read_text(file_record.path))
        return ParsedDocument(text=text, status=ParseStatus.OK)
