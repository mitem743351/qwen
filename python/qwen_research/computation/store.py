"""SQLite computation-metadata store.

Stores computation requests and results (metadata only — large artifacts live
in the controlled artifact directory). SQL is confined here; schema versioning
makes the store rebuildable and restart-safe.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import cast

from qwen_research.common.ids import ComputationId, SessionId, TaskId
from qwen_research.common.serialization import dumps, loads
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationRequest,
    ComputationResult,
    ComputationStatus,
    ExecutionProfile,
    ResultType,
)

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS computation_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS computations (
        computation_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        task_id TEXT,
        session_id TEXT,
        operation TEXT NOT NULL,
        execution_profile TEXT NOT NULL,
        requested_output TEXT,
        deterministic INTEGER NOT NULL,
        seed INTEGER,
        parameters TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_computations_project ON computations (project_id)",
    """CREATE TABLE IF NOT EXISTS computation_inputs (
        computation_id TEXT NOT NULL,
        idx INTEGER NOT NULL,
        reference TEXT NOT NULL,
        PRIMARY KEY (computation_id, idx)
    )""",
    """CREATE TABLE IF NOT EXISTS computation_results (
        computation_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        operation TEXT NOT NULL,
        result_type TEXT NOT NULL,
        value_json TEXT,
        rows INTEGER NOT NULL,
        metrics TEXT NOT NULL,
        artifact_refs TEXT NOT NULL,
        provenance TEXT NOT NULL,
        runtime_metadata TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        error TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_results_project ON computation_results (project_id)",
)


class ComputationStore:
    """SQLite implementation of computation persistence."""

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
                "INSERT OR REPLACE INTO computation_meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> ComputationStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ------------------------------------------------------------

    def save_request(self, request: ComputationRequest) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO computations
                    (computation_id, project_id, task_id, session_id, operation,
                     execution_profile, requested_output, deterministic, seed,
                     parameters, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.computation_id,
                    request.project_id,
                    request.task_id,
                    request.session_id,
                    request.operation.value,
                    request.execution_profile.value,
                    request.requested_output.value if request.requested_output else None,
                    int(request.deterministic),
                    request.seed,
                    json.dumps(request.parameters, default=str),
                    request.created_at.isoformat(),
                ),
            )
            db.execute(
                "DELETE FROM computation_inputs WHERE computation_id = ?",
                (request.computation_id,),
            )
            for i, ref in enumerate(request.input_refs):
                db.execute(
                    "INSERT INTO computation_inputs (computation_id, idx, reference) "
                    "VALUES (?, ?, ?)",
                    (request.computation_id, i, dumps(ref)),
                )

    def save_result(self, result: ComputationResult) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO computation_results
                    (computation_id, project_id, status, operation, result_type,
                     value_json, rows, metrics, artifact_refs, provenance,
                     runtime_metadata, started_at, completed_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.computation_id,
                    result.project_id,
                    result.status.value,
                    result.operation.value,
                    result.result_type.value,
                    _dump_value(result.value),
                    result.rows,
                    json.dumps(result.metrics, default=str),
                    json.dumps(result.artifact_refs),
                    json.dumps(result.provenance),
                    json.dumps(result.runtime_metadata),
                    result.started_at.isoformat() if result.started_at else None,
                    result.completed_at.isoformat() if result.completed_at else None,
                    result.error,
                ),
            )

    # -- reads -------------------------------------------------------------

    def get_request(self, computation_id: str) -> ComputationRequest | None:
        row = self._db().execute(
            "SELECT * FROM computations WHERE computation_id = ?", (computation_id,)
        ).fetchone()
        if row is None:
            return None
        inputs = self._db().execute(
            "SELECT reference FROM computation_inputs WHERE computation_id = ? ORDER BY idx",
            (computation_id,),
        ).fetchall()
        return ComputationRequest(
            computation_id=ComputationId(row["computation_id"]),
            project_id=row["project_id"],
            task_id=TaskId(row["task_id"]) if row["task_id"] else None,
            session_id=SessionId(row["session_id"]) if row["session_id"] else None,
            operation=ComputationOperation(row["operation"]),
            input_refs=tuple(loads(r["reference"]) for r in inputs),
            parameters=json.loads(row["parameters"]),
            execution_profile=ExecutionProfile(row["execution_profile"]),
            requested_output=(
                ResultType(row["requested_output"]) if row["requested_output"] else None
            ),
            deterministic=bool(row["deterministic"]),
            seed=row["seed"],
            created_at=_parse(row["created_at"]),
        )

    def get_result(self, project_id: str, computation_id: str) -> ComputationResult | None:
        row = self._db().execute(
            "SELECT * FROM computation_results WHERE project_id = ? AND computation_id = ?",
            (project_id, computation_id),
        ).fetchone()
        return _result_from_row(row) if row else None

    def list_results(self, project_id: str) -> list[ComputationResult]:
        rows = self._db().execute(
            "SELECT * FROM computation_results WHERE project_id = ? ORDER BY completed_at",
            (project_id,),
        ).fetchall()
        return [_result_from_row(r) for r in rows]

    def get_project_computations(self, project_id: str) -> list[str]:
        rows = self._db().execute(
            "SELECT computation_id FROM computations WHERE project_id = ?", (project_id,)
        ).fetchall()
        return [r["computation_id"] for r in rows]

    def computation_ids_by_project(self) -> dict[str, frozenset[str]]:
        """Return ``{project_id: frozenset(computation_ids)}`` for all projects."""
        rows = self._db().execute(
            "SELECT project_id, computation_id FROM computations"
        ).fetchall()
        mapping: dict[str, set[str]] = {}
        for r in rows:
            mapping.setdefault(r["project_id"], set()).add(r["computation_id"])
        return {k: frozenset(v) for k, v in mapping.items()}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _result_from_row(row: sqlite3.Row) -> ComputationResult:
    return ComputationResult(
        computation_id=ComputationId(row["computation_id"]),
        project_id=row["project_id"],
        status=ComputationStatus(row["status"]),
        operation=ComputationOperation(row["operation"]),
        result_type=ResultType(row["result_type"]),
        value=_load_value(row["value_json"]),
        rows=row["rows"],
        metrics=json.loads(row["metrics"]),
        artifact_refs=tuple(json.loads(row["artifact_refs"])),
        provenance=json.loads(row["provenance"]),
        runtime_metadata=json.loads(row["runtime_metadata"]),
        started_at=_parse(row["started_at"]) if row["started_at"] else None,
        completed_at=_parse(row["completed_at"]) if row["completed_at"] else None,
        error=row["error"],
    )


def _dump_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple, str, int, float, bool)):
        return json.dumps(value, default=str)
    return json.dumps({"repr": repr(value)})


def _load_value(data: str | None) -> object | None:
    if data is None:
        return None
    return cast(object, json.loads(data))


__all__ = ["ComputationStore"]
