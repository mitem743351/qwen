"""SQLite-backed vector index (brute-force cosine).

Vectors are stored as JSON in a local SQLite table and searched with a
deterministic pure-Python cosine scan. This is a dependency-free, local,
single-machine backend appropriate for a small-to-medium corpus; ``sqlite-vec``
or ``FAISS`` are the documented future upgrades behind :class:`VectorIndex`
(do not optimize prematurely).
"""

from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from qwen_research.vector.interface import VectorHit, VectorRecord

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vectors (
        chunk_id        TEXT PRIMARY KEY,
        model           TEXT NOT NULL,
        version         TEXT NOT NULL,
        dimension       INTEGER NOT NULL,
        vector_json     TEXT NOT NULL,
        text_hash       TEXT NOT NULL,
        distance_metric TEXT NOT NULL DEFAULT 'cosine',
        normalization   TEXT NOT NULL DEFAULT 'l2'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vectors_model_version ON vectors (model, version)",
    """
    CREATE TABLE IF NOT EXISTS vector_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
)


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        raise ValueError("vector dimension mismatch")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SqliteVectorIndex:
    """SQLite-backed brute-force cosine vector index."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._write_lock = threading.Lock()

    def _db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
            self._connections.append(conn)
        return conn

    def initialize(self) -> None:
        db = self._db()
        with self._write_lock, db:
            for ddl in _SCHEMA_DDL:
                db.execute(ddl)
            db.execute(
                "INSERT OR REPLACE INTO vector_meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def upsert(self, records: Iterable[VectorRecord]) -> None:
        db = self._db()
        with self._write_lock, db:
            for record in records:
                db.execute(
                    """
                    INSERT OR REPLACE INTO vectors
                        (chunk_id, model, version, dimension, vector_json,
                         text_hash, distance_metric, normalization)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.chunk_id,
                        record.model,
                        record.version,
                        record.dimension,
                        json.dumps(record.vector, separators=(",", ":")),
                        record.text_hash,
                        record.distance_metric,
                        record.normalization,
                    ),
                )

    def delete(self, chunk_ids: Iterable[str]) -> int:
        db = self._db()
        count = 0
        with self._write_lock, db:
            for chunk_id in chunk_ids:
                cur = db.execute("DELETE FROM vectors WHERE chunk_id = ?", (chunk_id,))
                count += cur.rowcount
        return count

    def search(
        self, vector: tuple[float, ...], *, model: str, version: str, limit: int
    ) -> list[VectorHit]:
        rows = self._db().execute(
            "SELECT chunk_id, vector_json FROM vectors WHERE model = ? AND version = ?",
            (model, version),
        ).fetchall()
        hits: list[VectorHit] = []
        for row in rows:
            stored = tuple(json.loads(row["vector_json"]))
            hits.append(VectorHit(chunk_id=row["chunk_id"], score=_cosine(vector, stored)))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: max(0, limit)]

    def get(self, chunk_id: str) -> VectorRecord | None:
        row = self._db().execute(
            "SELECT * FROM vectors WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return None
        return VectorRecord(
            chunk_id=row["chunk_id"],
            model=row["model"],
            version=row["version"],
            dimension=row["dimension"],
            vector=tuple(json.loads(row["vector_json"])),
            text_hash=row["text_hash"],
            distance_metric=row["distance_metric"],
            normalization=row["normalization"],
        )

    def list_ids(self, *, model: str | None = None, version: str | None = None) -> list[str]:
        if model is not None and version is not None:
            rows = self._db().execute(
                "SELECT chunk_id FROM vectors WHERE model = ? AND version = ?",
                (model, version),
            ).fetchall()
        elif model is not None:
            rows = self._db().execute(
                "SELECT chunk_id FROM vectors WHERE model = ?", (model,)
            ).fetchall()
        else:
            rows = self._db().execute("SELECT chunk_id FROM vectors").fetchall()
        return [r["chunk_id"] for r in rows]

    def stats(self) -> dict[str, int]:
        db = self._db()
        total = db.execute("SELECT COUNT(*) AS n FROM vectors").fetchone()["n"]
        models = db.execute("SELECT COUNT(DISTINCT model) AS n FROM vectors").fetchone()["n"]
        return {"vectors": total, "models": models}

    def rebuild(self) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute("DELETE FROM vectors")

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteVectorIndex:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
