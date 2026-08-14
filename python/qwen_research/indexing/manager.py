"""Index manager: orchestrates scan → parse → chunk → index.

Idempotent and incremental: unchanged files are skipped, changed files are
reprocessed, missing files are marked stale (not deleted), and re-running
against an unchanged corpus never duplicates documents or chunks.
"""

from __future__ import annotations

import dataclasses
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from time import monotonic

from qwen_research.corpus.config import CorpusConfig
from qwen_research.corpus.records import (
    Chunk,
    Document,
    DocumentContent,
    DocumentSection,
    FileRecord,
    FileStatus,
    ParseStatus,
)
from qwen_research.corpus.scanner import Scanner
from qwen_research.documents.base import ParsedDocument, parser_for
from qwen_research.documents.chunking import ChunkOptions, chunk_text
from qwen_research.documents.code import CodeParser
from qwen_research.documents.csv import CsvParser
from qwen_research.documents.markdown import MarkdownParser
from qwen_research.documents.pdf import PdfParser
from qwen_research.documents.structured import JsonParser, YamlParser
from qwen_research.documents.text import PlainTextParser
from qwen_research.domain.errors import UnsupportedDocumentError
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.retrieval.models import CorpusStats, IndexStatus


@dataclasses.dataclass(frozen=True)
class IndexReport:
    """Counts produced by an indexing run."""

    scanned: int
    new: int
    changed: int
    unchanged: int
    missing: int
    unsupported: int
    too_large: int
    failed: int
    unextractable: int
    documents_indexed: int
    chunks_created: int
    duration_ms: float


def _document_id(root_id: str, relative_path: str) -> str:
    digest = hashlib.sha256(f"{root_id}:{relative_path}".encode()).hexdigest()
    return f"doc_{digest[:24]}"


def _source_id(root_id: str, relative_path: str) -> str:
    digest = hashlib.sha256(f"{root_id}:{relative_path}".encode()).hexdigest()
    return f"src_{digest[:24]}"


def _title(record: FileRecord, parsed: ParsedDocument) -> str:
    title = parsed.metadata.get("title")
    if title:
        return title
    return Path(record.relative_path).stem


def register_default_parsers() -> None:
    """Register the Phase 3 parser adapters."""
    from qwen_research.documents.base import register_parser

    register_parser(PlainTextParser())
    register_parser(MarkdownParser())
    register_parser(JsonParser())
    register_parser(YamlParser())
    register_parser(CodeParser())
    register_parser(CsvParser())
    register_parser(PdfParser())


class IndexManager:
    """Coordinates the scanner, parsers, chunker, and index."""

    def __init__(self, config: CorpusConfig, index: CorpusIndex) -> None:
        self._config = config
        self._index = index
        self._scanner = Scanner(config)
        self._workers = max(1, config.indexing_workers)
        register_default_parsers()

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        self._index.initialize()
        self._index.upsert_roots(
            (
                r.root_id,
                r.path,
                r.name,
                r.read_only,
                r.recursive,
            )
            for r in self._config.roots
        )

    def index_all(self, *, root_ids: tuple[str, ...] | None = None) -> IndexReport:
        """Scan all roots and incrementally index new/changed files."""
        started = monotonic()
        self.initialize()
        known = self._index.document_hash_map()
        scan = self._scanner.scan(known_hashes=known, root_ids=root_ids)

        to_process = [
            r for r in scan.records if r.status in (FileStatus.NEW, FileStatus.MODIFIED)
        ]
        missing_paths = [
            (r.root_id, r.relative_path)
            for r in scan.records
            if r.status is FileStatus.MISSING
        ]

        documents_indexed = 0
        chunks_created = 0
        failed = 0
        unextractable = 0

        # Parse in a bounded worker pool (I/O + normalization); writes happen
        # sequentially on the main thread for SQLite/FTS consistency.
        parsed: dict[str, ParsedDocument | Exception] = {}
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            future_by_rel = {
                pool.submit(self._parse_one, record): record.relative_path
                for record in to_process
            }
            for future in future_by_rel:
                rel = future_by_rel[future]
                try:
                    parsed[rel] = future.result()
                except Exception as exc:  # noqa: BLE001 — safety net
                    parsed[rel] = exc

        for record in to_process:
            outcome = parsed[record.relative_path]
            if isinstance(outcome, Exception):
                failed += 1
                continue
            if outcome.status is ParseStatus.UNEXTRACTABLE:
                unextractable += 1
            self._upsert(record, outcome)
            documents_indexed += 1
            chunks_created += self._chunk_count(record, outcome)

        self._index.mark_missing(missing_paths)

        now = monotonic()
        self._index.set_metadata("last_scan_time", _now_iso())
        self._index.set_metadata("last_index_time", _now_iso())

        return IndexReport(
            scanned=scan.scanned,
            new=scan.new,
            changed=scan.changed,
            unchanged=scan.unchanged,
            missing=scan.missing,
            unsupported=scan.unsupported,
            too_large=scan.too_large,
            failed=failed,
            unextractable=unextractable,
            documents_indexed=documents_indexed,
            chunks_created=chunks_created,
            duration_ms=(now - started) * 1000,
        )

    def rebuild(self) -> IndexReport:
        """Drop all documents and re-index from scratch."""
        self._index.clear()
        return self.index_all()

    def remove_stale(self) -> int:
        return self._index.remove_stale()

    def stats(self) -> CorpusStats:
        return self._index.stats()

    def status(self) -> IndexStatus:
        return self._index.status()

    # -- internals ---------------------------------------------------------

    def _parse_one(self, record: FileRecord) -> ParsedDocument | Exception:
        parser = parser_for(record.media_type)
        if parser is None:
            return UnsupportedDocumentError(
                f"unsupported media type {record.media_type!r}"
            )
        try:
            return parser.parse(record)
        except Exception as exc:  # noqa: BLE001 — parsers raise domain errors
            return exc

    def _upsert(self, record: FileRecord, parsed: ParsedDocument) -> None:
        document_id = _document_id(record.root_id, record.relative_path)
        source_id = _source_id(record.root_id, record.relative_path)
        metadata = dict(parsed.metadata)
        metadata["parse_status"] = parsed.status.value

        document = Document(
            document_id=document_id,
            source_id=source_id,
            path=record.path,
            root_id=record.root_id,
            relative_path=record.relative_path,
            media_type=record.media_type,
            title=_title(record, parsed),
            metadata=metadata,
            content_hash=record.content_hash,
            size_bytes=record.size_bytes,
            modified_at=record.modified_at,
        )

        sections = tuple(
            DocumentSection(
                section_id=f"{document_id}#{section.section_id}",
                document_id=document_id,
                page=section.page,
                heading=section.heading,
                start_offset=section.start_offset,
                end_offset=section.end_offset,
            )
            for section in parsed.sections
        )

        chunks: list[Chunk] = []
        if parsed.text.strip():
            chunks = chunk_text(
                parsed.text,
                document_id=document_id,
                source_id=source_id,
                options=ChunkOptions(
                    chunk_size=self._config.chunk_size,
                    chunk_overlap=self._config.chunk_overlap,
                ),
                sections=sections,
            )

        self._index.upsert_document(
            document,
            DocumentContent(document_id=document_id, text=parsed.text, sections=sections),
            chunks,
            list(sections),
        )

    def _chunk_count(self, record: FileRecord, parsed: ParsedDocument) -> int:
        if not parsed.text.strip():
            return 0
        document_id = _document_id(record.root_id, record.relative_path)
        source_id = _source_id(record.root_id, record.relative_path)
        return len(
            chunk_text(
                parsed.text,
                document_id=document_id,
                source_id=source_id,
                options=ChunkOptions(
                    chunk_size=self._config.chunk_size,
                    chunk_overlap=self._config.chunk_overlap,
                ),
                sections=parsed.sections,
            )
        )


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
