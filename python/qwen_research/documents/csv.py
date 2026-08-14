"""CSV parser.

Rows are rendered as ``header: value`` lines so that values remain searchable
and citable. The header row is used for column names when present.
"""

from __future__ import annotations

import csv
import io

from qwen_research.corpus.records import FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.documents.text import read_text


class CsvParser:
    """Parses CSV files (``text/csv``)."""

    media_types: tuple[str, ...] = ("text/csv",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        text = read_text(file_record.path)
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ParsedDocument(text="", status=ParseStatus.OK)
        header = [c.strip() for c in rows[0]]
        lines: list[str] = []
        for row in rows[1:]:
            parts = [
                f"{header[i] if i < len(header) else f'col{i}'}: {cell}"
                for i, cell in enumerate(row)
            ]
            lines.append(" | ".join(parts))
        return ParsedDocument(text=normalize_text("\n".join(lines)), status=ParseStatus.OK)
