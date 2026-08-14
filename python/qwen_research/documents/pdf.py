"""PDF parser.

Extracts per-page text while preserving page boundaries (essential for
citations) and document metadata. No OCR: a PDF with no extractable text
returns ``ParseStatus.UNEXTRACTABLE`` rather than an empty document.
"""

from __future__ import annotations

from qwen_research.corpus.records import DocumentSection, FileRecord, ParseStatus
from qwen_research.documents.base import ParsedDocument
from qwen_research.documents.normalization import normalize_text
from qwen_research.domain.errors import DocumentParseError


class PdfParser:
    """Parses PDF files (``application/pdf``) with page boundaries preserved."""

    media_types: tuple[str, ...] = ("application/pdf",)

    def supports(self, media_type: str) -> bool:
        return media_type in self.media_types

    def parse(self, file_record: FileRecord) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency present
            raise DocumentParseError("pypdf is not installed") from exc

        try:
            reader = PdfReader(file_record.path)
        except Exception as exc:  # noqa: BLE001 — malformed PDFs raise many types
            raise DocumentParseError(f"could not open PDF: {exc}") from exc

        meta = reader.metadata
        metadata: dict[str, str] = {}
        for key in ("author", "subject", "creator", "title"):
            value = getattr(meta, key, None) if meta is not None else None
            if value:
                metadata[key] = str(value)
        metadata["page_count"] = str(len(reader.pages))

        pages: list[str] = []
        sections: list[DocumentSection] = []
        offset = 0
        extracted_any = False
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — per-page extraction can fail
                page_text = ""
            page_text = normalize_text(page_text)
            if page_text:
                extracted_any = True
            pages.append(page_text)
            start = offset
            offset += len(page_text) + 1
            sections.append(
                DocumentSection(
                    section_id=f"page-{i + 1}",
                    document_id="",
                    page=i + 1,
                    heading=None,
                    start_offset=start,
                    end_offset=offset - 1,
                )
            )

        if not extracted_any:
            return ParsedDocument(
                text="",
                sections=tuple(sections),
                metadata=metadata,
                status=ParseStatus.UNEXTRACTABLE,
            )

        return ParsedDocument(
            text="\n".join(pages),
            sections=tuple(sections),
            metadata=metadata,
            status=ParseStatus.OK,
        )
