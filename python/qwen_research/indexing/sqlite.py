"""SQLite + FTS5 implementation of :class:`CorpusIndex`.

The retrieval subsystem uses only the :class:`CorpusIndex` interface; it never
touches SQL. A single local database holds corpus metadata, documents, sections,
chunks, and the FTS5 index.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from qwen_research.corpus.records import Chunk, Document, DocumentContent, DocumentSection
from qwen_research.indexing.schema import SCHEMA_DDL, SCHEMA_TRIGGERS, SCHEMA_VERSION
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexState,
    IndexStatus,
    RetrievedChunk,
    SearchFilters,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _fts_query(query: str) -> str:
    """Build a safe FTS5 query by quoting each whitespace token as a phrase.

    Each token is wrapped in double quotes and any embedded ``"`` is doubled
    (FTS5's escape for a literal quote), so a user query can never inject FTS5
    syntax (``AND``/``OR``/``NEAR``/``*``/``^``/parentheses) — every token is
    searched as a literal phrase.
    """
    tokens = [t for t in query.split() if t]
    return " ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def _escape_like(prefix: str) -> str:
    """Escape LIKE wildcards so *prefix* is matched literally."""
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqliteCorpusIndex:
    """SQLite-backed corpus index with FTS5 lexical search.

    Uses thread-local connections so that MCP tool handlers (which run in
    worker threads) can read the index safely while the manager indexes from
    the main thread. Writes are serialized with a lock; WAL mode allows
    concurrent readers.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._write_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    def _db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            self._connections.append(conn)
        return conn

    def initialize(self) -> None:
        db = self._db()
        with self._write_lock, db:
            for ddl in SCHEMA_DDL:
                db.execute(ddl)
            # Minimal schema-version migration: v1 indexed ``relative_path`` as
            # globally unique, which breaks multi-root identity. v2 keys on
            # ``(root_id, relative_path)``. The index is a rebuildable cache, so
            # migrating drops and recreates the document tables (forcing a
            # re-index on the next run) rather than preserving stale rows.
            row = db.execute(
                "SELECT value FROM index_metadata WHERE key = 'schema_version'"
            ).fetchone()
            current = int(row["value"]) if row else 0
            if current == 1:
                for trigger in ("chunks_ai", "chunks_ad", "chunks_au"):
                    db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                for table in ("chunks_fts", "chunks", "document_sections", "documents"):
                    db.execute(f"DROP TABLE IF EXISTS {table}")
                for ddl in SCHEMA_DDL:
                    db.execute(ddl)
            for trigger in SCHEMA_TRIGGERS:
                db.execute(trigger)
            db.execute(
                "INSERT OR REPLACE INTO index_metadata (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def upsert_roots(self, roots: Iterable[tuple[str, str, str | None, bool, bool]]) -> None:
        db = self._db()
        with self._write_lock, db:
            for root_id, path, name, read_only, recursive in roots:
                db.execute(
                    """
                        INSERT OR REPLACE INTO corpus_roots
                            (root_id, path, name, read_only, recursive)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                    (root_id, path, name, int(read_only), int(recursive)),
                )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteCorpusIndex:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ------------------------------------------------------------

    def upsert_document(
        self,
        document: Document,
        content: DocumentContent,
        chunks: list[Chunk],
        sections: list[DocumentSection],
    ) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document.document_id,))
            db.execute(
                "DELETE FROM document_sections WHERE document_id = ?",
                (document.document_id,),
            )
            db.execute(
                """
                INSERT OR REPLACE INTO documents
                    (document_id, source_id, root_id, relative_path, media_type,
                     title, metadata, content_hash, size_bytes, modified_at,
                     stale, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    document.document_id,
                    document.source_id,
                    document.root_id,
                    document.relative_path,
                    document.media_type,
                    document.title,
                    json.dumps(document.metadata, sort_keys=True),
                    document.content_hash,
                    document.size_bytes,
                    document.modified_at.isoformat() if document.modified_at else None,
                    _now_iso(),
                ),
            )
            for section in sections:
                db.execute(
                    """
                    INSERT OR REPLACE INTO document_sections
                        (section_id, document_id, page, heading, start_offset, end_offset)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section.section_id,
                        document.document_id,
                        section.page,
                        section.heading,
                        section.start_offset,
                        section.end_offset,
                    ),
                )
            for chunk in chunks:
                db.execute(
                    """
                    INSERT INTO chunks
                        (chunk_id, document_id, source_id, text, page, section,
                         start_offset, end_offset)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source_id,
                        chunk.text,
                        chunk.page,
                        chunk.section,
                        chunk.start_offset,
                        chunk.end_offset,
                    ),
                )

    def mark_missing(self, paths: Iterable[tuple[str, str]]) -> int:
        db = self._db()
        count = 0
        with self._write_lock, db:
            for root_id, rel in paths:
                cur = db.execute(
                    "UPDATE documents SET stale = 1 "
                    "WHERE root_id = ? AND relative_path = ? AND stale = 0",
                    (root_id, rel),
                )
                count += cur.rowcount
        return count

    def remove_document(self, document_id: str) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            db.execute("DELETE FROM document_sections WHERE document_id = ?", (document_id,))
            db.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))

    def remove_stale(self) -> int:
        db = self._db()
        with self._write_lock, db:
            rows = db.execute("SELECT document_id FROM documents WHERE stale = 1").fetchall()
            for row in rows:
                db.execute("DELETE FROM chunks WHERE document_id = ?", (row["document_id"],))
                db.execute(
                    "DELETE FROM document_sections WHERE document_id = ?",
                    (row["document_id"],),
                )
            cur = db.execute("DELETE FROM documents WHERE stale = 1")
            return cur.rowcount

    def clear(self) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute("DELETE FROM chunks")
            db.execute("DELETE FROM document_sections")
            db.execute("DELETE FROM documents")

    # -- reads -------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int,
        offset: int = 0,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        fts = _fts_query(query)
        if not fts:
            return []
        db = self._db()
        clauses = ["chunks_fts MATCH ?"]
        params: list[object] = [fts]
        filters = filters or SearchFilters()
        if filters.roots:
            clauses.append("d.root_id IN ({})".format(",".join("?" * len(filters.roots))))
            params.extend(filters.roots)
        if filters.document_types:
            clauses.append(
                "d.media_type IN ({})".format(",".join("?" * len(filters.document_types)))
            )
            params.extend(filters.document_types)
        if filters.path_prefix:
            prefix = filters.path_prefix.rstrip("/")
            if prefix:
                # Boundary semantics: match the prefix itself or any child under
                # it (``prefix/...``), as a *literal* prefix — ``%``/``_`` are
                # escaped so the value is never treated as a LIKE pattern.
                escaped = _escape_like(prefix)
                clauses.append(
                    "(d.relative_path = ? OR d.relative_path LIKE ? ESCAPE '\\')"
                )
                params.append(prefix)
                params.append(f"{escaped}/%")
        where = " AND ".join(clauses)
        sql = f"""
            SELECT c.chunk_id, c.document_id, c.source_id, c.text, c.page, c.section,
                   c.start_offset, c.end_offset, d.relative_path, d.root_id, d.media_type,
                   bm25(chunks_fts) AS bm25
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            JOIN documents d ON d.document_id = c.document_id
            WHERE {where}
            ORDER BY bm25
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = db.execute(sql, params).fetchall()
        results: list[RetrievedChunk] = []
        for row in rows:
            results.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    source_id=row["source_id"],
                    text=row["text"],
                    # bm25 is lower-is-better; expose higher-is-better.
                    score=-float(row["bm25"]),
                    page=row["page"],
                    section=row["section"],
                    path=row["relative_path"],
                    root_id=row["root_id"],
                    relative_path=row["relative_path"],
                    media_type=row["media_type"],
                )
            )
        return results

    def get_document(self, document_id: str) -> DocumentView | None:
        db = self._db()
        row = db.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return None
        section_rows = db.execute(
            "SELECT page, heading FROM document_sections "
            "WHERE document_id = ? ORDER BY start_offset",
            (document_id,),
        ).fetchall()
        return DocumentView(
            document_id=row["document_id"],
            source_id=row["source_id"],
            root_id=row["root_id"],
            relative_path=row["relative_path"],
            display_path=row["relative_path"],
            media_type=row["media_type"],
            title=row["title"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            content_hash=row["content_hash"],
            size_bytes=row["size_bytes"],
            modified_at=_parse_dt(row["modified_at"]),
            sections=tuple((r["page"], r["heading"]) for r in section_rows),
        )

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        row = self._db().execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return None
        return Chunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            source_id=row["source_id"],
            text=row["text"],
            page=row["page"],
            section=row["section"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
        )

    def list_chunks(self) -> list[Chunk]:
        rows = self._db().execute(
            "SELECT * FROM chunks ORDER BY chunk_id"
        ).fetchall()
        return [
            Chunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                source_id=r["source_id"],
                text=r["text"],
                page=r["page"],
                section=r["section"],
                start_offset=r["start_offset"],
                end_offset=r["end_offset"],
            )
            for r in rows
        ]

    def get_chunks_for_ids(self, chunk_ids: Iterable[str]) -> list[RetrievedChunk]:
        ids = list(chunk_ids)
        if not ids:
            return []
        db = self._db()
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"""
            SELECT c.chunk_id, c.document_id, c.source_id, c.text, c.page, c.section,
                   d.relative_path, d.root_id, d.media_type
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.chunk_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        by_id = {r["chunk_id"]: r for r in rows}
        return [
            RetrievedChunk(
                chunk_id=cid,
                document_id=by_id[cid]["document_id"],
                source_id=by_id[cid]["source_id"],
                text=by_id[cid]["text"],
                score=0.0,
                page=by_id[cid]["page"],
                section=by_id[cid]["section"],
                path=by_id[cid]["relative_path"],
                root_id=by_id[cid]["root_id"],
                relative_path=by_id[cid]["relative_path"],
                media_type=by_id[cid]["media_type"],
            )
            for cid in ids
            if cid in by_id
        ]

    def list_documents(self) -> list[Document]:
        rows = self._db().execute("SELECT * FROM documents ORDER BY relative_path").fetchall()
        return [
            Document(
                document_id=r["document_id"],
                source_id=r["source_id"],
                path=r["relative_path"],
                root_id=r["root_id"],
                relative_path=r["relative_path"],
                media_type=r["media_type"],
                title=r["title"],
                metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                content_hash=r["content_hash"],
                size_bytes=r["size_bytes"],
                modified_at=_parse_dt(r["modified_at"]),
            )
            for r in rows
        ]

    def document_hash_map(self) -> dict[tuple[str, str], str]:
        rows = self._db().execute(
            "SELECT root_id, relative_path, content_hash FROM documents"
        ).fetchall()
        return {(r["root_id"], r["relative_path"]): r["content_hash"] for r in rows}

    def stats(self) -> CorpusStats:
        db = self._db()
        roots = db.execute("SELECT COUNT(*) AS n FROM corpus_roots").fetchone()["n"]
        docs = db.execute("SELECT COUNT(*) AS n FROM documents WHERE stale = 0").fetchone()["n"]
        chunks = db.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        bytes_ = db.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) AS n FROM documents WHERE stale = 0"
        ).fetchone()["n"]
        stale = db.execute("SELECT COUNT(*) AS n FROM documents WHERE stale = 1").fetchone()["n"]
        last = db.execute(
            "SELECT value FROM index_metadata WHERE key = 'last_index_time'"
        ).fetchone()
        return CorpusStats(
            roots=roots,
            documents=docs,
            chunks=chunks,
            indexed_bytes=bytes_,
            last_index_time=_parse_dt(last["value"]) if last else None,
            failures=0,
            stale_documents=stale,
        )

    def status(self) -> IndexStatus:
        db = self._db()
        docs = db.execute("SELECT COUNT(*) AS n FROM documents WHERE stale = 0").fetchone()["n"]
        chunks = db.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        stale = db.execute("SELECT COUNT(*) AS n FROM documents WHERE stale = 1").fetchone()["n"]
        last_scan = db.execute(
            "SELECT value FROM index_metadata WHERE key = 'last_scan_time'"
        ).fetchone()
        last_success = db.execute(
            "SELECT value FROM index_metadata WHERE key = 'last_index_time'"
        ).fetchone()
        state = IndexState.READY if chunks >= 0 else IndexState.NOT_INITIALIZED
        return IndexStatus(
            state=state,
            last_scan=_parse_dt(last_scan["value"]) if last_scan else None,
            last_success=_parse_dt(last_success["value"]) if last_success else None,
            documents=docs,
            chunks=chunks,
            failures=0,
            stale=stale,
        )

    def set_metadata(self, key: str, value: str) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
                (key, value),
            )
