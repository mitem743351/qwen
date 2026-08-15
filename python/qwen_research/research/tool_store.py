"""Tool-execution result persistence (Phase 9.3).

Concrete implementations of the ``ToolExecutionStore`` protocol (declared in
``tool_loop.py``), keyed by ``(inference_session_id, call_id)`` so a resumed
workflow reuses a completed result instead of executing the same call twice.

Only safe metadata is persisted (status, bounded content, error, duration,
provenance); hidden reasoning is never stored (it lives on ``InferenceResult`` /
``Message`` as a ``transient`` field that the serializer drops).
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

from qwen_research.common.serialization import dumps, loads
from qwen_research.research.tool_loop import ToolExecutionResult


class InMemoryToolExecutionStore:
    """An ephemeral in-memory store (tests and short-lived sessions)."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str], ToolExecutionResult] = {}

    def save(
        self, inference_session_id: str, call_id: str, result: ToolExecutionResult
    ) -> None:
        self._results[(inference_session_id, call_id)] = result

    def get(
        self, inference_session_id: str, call_id: str
    ) -> ToolExecutionResult | None:
        return self._results.get((inference_session_id, call_id))


class SqliteToolExecutionStore:
    """A SQLite-backed tool-execution store (restart-safe)."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._write_lock = threading.Lock()

    def _db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
            self._connections.append(conn)
        return conn

    def initialize(self) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS tool_executions (
                    inference_session_id TEXT NOT NULL,
                    call_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (inference_session_id, call_id)
                )"""
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteToolExecutionStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(
        self, inference_session_id: str, call_id: str, result: ToolExecutionResult
    ) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO tool_executions
                   (inference_session_id, call_id, data) VALUES (?, ?, ?)""",
                (inference_session_id, call_id, dumps(result)),
            )

    def get(
        self, inference_session_id: str, call_id: str
    ) -> ToolExecutionResult | None:
        row = self._db().execute(
            "SELECT data FROM tool_executions WHERE inference_session_id = ? AND call_id = ?",
            (inference_session_id, call_id),
        ).fetchone()
        if row is None:
            return None
        result = loads(row[0])
        return result if isinstance(result, ToolExecutionResult) else None
