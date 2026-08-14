"""SQLite schema for the corpus index.

A single local database holds corpus metadata, documents, sections, chunks,
and an FTS5 index. A minimal ``schema_version`` mechanism records the schema
revision; no sophisticated migration framework is introduced in Phase 3.
"""

from __future__ import annotations

SCHEMA_VERSION = 2

#: DDL statements, executed in order during initialization.
SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS corpus_roots (
        root_id     TEXT PRIMARY KEY,
        path        TEXT NOT NULL,
        name        TEXT,
        read_only   INTEGER NOT NULL DEFAULT 1,
        recursive   INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id   TEXT PRIMARY KEY,
        source_id     TEXT NOT NULL,
        root_id       TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        media_type    TEXT NOT NULL,
        title         TEXT NOT NULL,
        metadata      TEXT NOT NULL DEFAULT '{}',
        content_hash  TEXT NOT NULL,
        size_bytes    INTEGER NOT NULL,
        modified_at   TEXT,
        stale         INTEGER NOT NULL DEFAULT 0,
        indexed_at    TEXT NOT NULL,
        UNIQUE (root_id, relative_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_sections (
        section_id   TEXT PRIMARY KEY,
        document_id  TEXT NOT NULL,
        page         INTEGER,
        heading      TEXT,
        start_offset INTEGER NOT NULL,
        end_offset   INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id     TEXT PRIMARY KEY,
        document_id  TEXT NOT NULL,
        source_id    TEXT NOT NULL,
        text         TEXT NOT NULL,
        page         INTEGER,
        section      TEXT,
        start_offset INTEGER NOT NULL,
        end_offset   INTEGER NOT NULL
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        text,
        content='chunks',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS index_metadata (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
)

#: Triggers to keep the FTS5 index in sync with ``chunks``.
SCHEMA_TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
        INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
        INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
    END
    """,
)
