"""Regression: multi-root incremental identity.

Two roots may contain the same relative path. Document identity is
``(root_id, relative_path)``; the incremental hash map and stale-marking must
key on both, never on relative path alone.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from qwen_research.corpus.config import CorpusConfig, CorpusRoot
from qwen_research.indexing.manager import IndexManager
from qwen_research.indexing.sqlite import SqliteCorpusIndex


def _config(root_a: Path, root_b: Path) -> CorpusConfig:
    return CorpusConfig(
        roots=(
            CorpusRoot(root_id="a", path=str(root_a), read_only=True, recursive=True),
            CorpusRoot(root_id="b", path=str(root_b), read_only=True, recursive=True),
        )
    )


def _index(tmp_path: Path, config: CorpusConfig) -> tuple[SqliteCorpusIndex, IndexManager]:
    index = SqliteCorpusIndex(tmp_path / "corpus.db")
    manager = IndexManager(config, index)
    manager.initialize()
    return index, manager


def test_same_relative_path_gets_distinct_identity(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "note.txt").write_text("alpha content")
    (root_b / "note.txt").write_text("beta content")

    index, manager = _index(tmp_path, _config(root_a, root_b))
    manager.index_all()

    docs = index.list_documents()
    by_path = {(d.root_id, d.relative_path): d for d in docs}
    assert ("a", "note.txt") in by_path
    assert ("b", "note.txt") in by_path
    assert by_path[("a", "note.txt")].document_id != by_path[("b", "note.txt")].document_id


def test_modifying_one_root_does_not_reindex_the_other(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "note.txt").write_text("alpha")
    (root_b / "note.txt").write_text("beta")

    index, manager = _index(tmp_path, _config(root_a, root_b))
    manager.index_all()

    # Modify only root a's file; root b's identical-named file must be
    # classified UNCHANGED, not conflated with a.
    (root_a / "note.txt").write_text("alpha changed")
    report = manager.index_all()

    assert report.changed == 1
    assert report.unchanged == 1  # root b's note.txt


def test_deleting_one_root_file_does_not_stale_the_other(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "note.txt").write_text("alpha")
    (root_b / "note.txt").write_text("beta")

    index, manager = _index(tmp_path, _config(root_a, root_b))
    manager.index_all()

    (root_a / "note.txt").unlink()
    manager.index_all()

    # Only root a's document is stale; root b's survives (non-stale).
    stats = index.stats()
    assert stats.stale_documents == 1
    assert stats.documents == 1  # only root b remains non-stale

    # And root b's document is still present with its original content hash.
    hm = index.document_hash_map()
    assert ("b", "note.txt") in hm


def test_hash_map_is_keyed_by_root(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "note.txt").write_text("alpha")
    (root_b / "note.txt").write_text("beta")

    index, manager = _index(tmp_path, _config(root_a, root_b))
    manager.index_all()

    hm = index.document_hash_map()
    assert ("a", "note.txt") in hm
    assert ("b", "note.txt") in hm
    assert hm[("a", "note.txt")] != hm[("b", "note.txt")]


def test_v1_schema_migrates_to_composite_unique(tmp_path: Path) -> None:
    """An existing v1 index (single-column UNIQUE on relative_path) is migrated
    so two roots may share a relative path."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE documents (
            document_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, root_id TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL,
            title TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            modified_at TEXT, stale INTEGER NOT NULL DEFAULT 0, indexed_at TEXT NOT NULL)"""
    )
    conn.execute(
        "CREATE TABLE document_sections (section_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,"
        " page INTEGER, heading TEXT, start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,"
        " source_id TEXT NOT NULL, text TEXT NOT NULL, page INTEGER, section TEXT,"
        " start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL)"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='rowid')"
    )
    conn.execute("CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO index_metadata VALUES ('schema_version', '1')")
    conn.commit()
    conn.close()

    index = SqliteCorpusIndex(db_path)
    index.initialize()

    check = sqlite3.connect(db_path)
    version = check.execute(
        "SELECT value FROM index_metadata WHERE key = 'schema_version'"
    ).fetchone()[0]
    assert version == "2"
    # The new schema accepts the same relative path under two roots.
    for doc_id, src, root_id in (("d1", "s1", "a"), ("d2", "s2", "b")):
        check.execute(
            "INSERT INTO documents (document_id, source_id, root_id, relative_path,"
            " media_type, title, metadata, content_hash, size_bytes, stale, indexed_at)"
            " VALUES (?, ?, ?, 'note.txt', 'text/plain', 'n', '{}', 'h', 1, 0, 'now')",
            (doc_id, src, root_id),
        )
    check.commit()
    count = check.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    check.close()
    assert count == 2
