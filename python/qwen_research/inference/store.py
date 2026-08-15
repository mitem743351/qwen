"""Inference invocation metadata persistence (no secrets, no hidden reasoning).

Only structured metadata is stored: provider, model, profile, status, usage,
finish reason, capability decisions, timestamps, retry count. Request/response
content and hidden chain-of-thought are never persisted.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from qwen_research.common.serialization import dumps, loads
from qwen_research.inference.models import InvocationMetadata

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS inference_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS inference_invocations (
        invocation_id TEXT PRIMARY KEY,
        task_id TEXT,
        session_id TEXT,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        profile TEXT NOT NULL,
        status TEXT NOT NULL,
        finish_reason TEXT NOT NULL,
        usage_json TEXT NOT NULL,
        capability_decisions_json TEXT NOT NULL,
        retry_count INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        latency_ms REAL,
        error TEXT,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_invocations_task ON inference_invocations (task_id)",
)


@runtime_checkable
class InvocationStore(Protocol):
    def save(self, metadata: InvocationMetadata) -> None: ...

    def get(self, invocation_id: str) -> InvocationMetadata | None: ...

    def list_for_task(self, task_id: str) -> list[InvocationMetadata]: ...


class SqliteInvocationStore:
    """SQLite implementation of :class:`InvocationStore`."""

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
                "INSERT OR REPLACE INTO inference_meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteInvocationStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, metadata: InvocationMetadata) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO inference_invocations
                   (invocation_id, task_id, session_id, provider, model, profile,
                    status, finish_reason, usage_json, capability_decisions_json,
                    retry_count, started_at, completed_at, latency_ms, error, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    metadata.invocation_id,
                    metadata.task_id,
                    metadata.session_id,
                    metadata.provider,
                    metadata.model,
                    metadata.profile,
                    metadata.status,
                    metadata.finish_reason,
                    json.dumps(metadata.usage, sort_keys=True),
                    json.dumps(metadata.capability_decisions, sort_keys=True),
                    metadata.retry_count,
                    metadata.started_at.isoformat(),
                    metadata.completed_at.isoformat() if metadata.completed_at else None,
                    metadata.latency_ms,
                    metadata.error,
                    dumps(metadata),
                ),
            )

    def get(self, invocation_id: str) -> InvocationMetadata | None:
        row = self._db().execute(
            "SELECT data FROM inference_invocations WHERE invocation_id = ?",
            (invocation_id,),
        ).fetchone()
        return loads(row["data"]) if row else None

    def list_for_task(self, task_id: str) -> list[InvocationMetadata]:
        rows = self._db().execute(
            "SELECT data FROM inference_invocations WHERE task_id = ? ORDER BY started_at",
            (task_id,),
        ).fetchall()
        return [loads(r["data"]) for r in rows]
