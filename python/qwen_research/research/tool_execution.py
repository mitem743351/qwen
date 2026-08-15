"""Transactional tool-execution reliability (Phase 9.4).

A local execution state machine around model-requested tool calls. The
execution identity is the immutable ``(inference_session_id, call_id)`` pair;
claims are atomic, lease-based, and durable, so a completed call is never
executed again for the same identity and a crash-ambiguous outcome is
represented explicitly as ``UNKNOWN`` rather than silently duplicated.

Guarantee provided (precise, not "exactly once"):

    For a successfully claimed call whose completion has been durably recorded,
    the runtime reuses that result and does not execute the call again for the
    same inference-session/call identity.

A crash after an external side effect but before durable completion is
represented as ``UNKNOWN`` — never as ``SUCCEEDED`` and never silently retried
for side-effecting tools.

No credentials and no hidden reasoning are persisted here. Only safe metadata
(tool name, argument hash, statuses, bounded content, provenance) is stored.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qwen_research.common.serialization import dumps, loads, serializable
from qwen_research.domain.errors import ToolError as DomainToolError
from qwen_research.research.tool_loop import ToolExecutionResult, ToolExecutionStatus


class LeaseOwnershipError(DomainToolError):
    """A lease operation was attempted by a non-owner or on an expired lease."""


class CallIdConflictError(DomainToolError):
    """A call id was reused with different tool/arguments/scope."""


class ToolExecutionState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    INVALID_ARGUMENTS = "invalid_arguments"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT = "resource_limit"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    ABANDONED = "abandoned"


class ToolExecutionSemantics(StrEnum):
    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    SIDE_EFFECTING = "side_effecting"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"


class ToolRecoveryPolicy(StrEnum):
    """Explicit recovery choices for stale/unknown executions.

    ``REUSE_TERMINAL`` (replaying a durable terminal result) is always applied;
    ``WAIT_FOR_ACTIVE`` is not yet implemented (no distributed wait). The two
    implemented policies govern what happens to a *stale* active claim.
    """

    RECLAIM_STALE_IF_SAFE = "reclaim_stale_if_safe"
    FAIL_ON_UNKNOWN = "fail_on_unknown"


class ClaimOutcome(StrEnum):
    CLAIMED = "claimed"
    ALREADY_COMPLETED = "already_completed"
    ALREADY_CLAIMED = "already_claimed"
    STALE = "stale"
    CONFLICT = "conflict"


_TERMINAL_STATES = frozenset(
    {
        ToolExecutionState.SUCCEEDED,
        ToolExecutionState.FAILED,
        ToolExecutionState.DENIED,
        ToolExecutionState.INVALID_ARGUMENTS,
        ToolExecutionState.TIMEOUT,
        ToolExecutionState.RESOURCE_LIMIT,
        ToolExecutionState.CANCELLED,
        ToolExecutionState.UNKNOWN,
    }
)

#: Terminal states whose recorded outcome is deterministic and safe to replay.
_REPLAYABLE_STATES = frozenset(
    {
        ToolExecutionState.SUCCEEDED,
        ToolExecutionState.DENIED,
        ToolExecutionState.INVALID_ARGUMENTS,
        ToolExecutionState.CANCELLED,
    }
)

#: Active (non-terminal) states.
_ACTIVE_STATES = frozenset(
    {ToolExecutionState.PENDING, ToolExecutionState.CLAIMED, ToolExecutionState.RUNNING}
)


def semantics_for_permission(permission: Any) -> ToolExecutionSemantics:
    """Map a permission class to a default execution semantics.

    Permissions (may this call execute?) and execution semantics (what happens
    if it runs twice / ambiguously?) are distinct axes. This is a conservative
    default; a tool may declare ``execution_semantics`` explicitly.
    """
    value = getattr(permission, "value", permission)
    return {
        "read": ToolExecutionSemantics.READ_ONLY,
        "analyze": ToolExecutionSemantics.IDEMPOTENT,
        "write": ToolExecutionSemantics.SIDE_EFFECTING,
        "execute": ToolExecutionSemantics.SIDE_EFFECTING,
        "destructive": ToolExecutionSemantics.DESTRUCTIVE,
    }.get(str(value), ToolExecutionSemantics.UNKNOWN)


def canonical_arguments_hash(arguments: dict[str, Any]) -> str:
    """Deterministic SHA-256 of canonically-serialized arguments.

    Key order is normalized so ``{"a":1,"b":2}`` and ``{"b":2,"a":1}`` hash
    identically. Python ``repr()`` is never used.
    """
    canonical = json.dumps(arguments, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@serializable
@dataclasses.dataclass(frozen=True)
class ToolExecutionIdentity:
    """The canonical, immutable execution identity."""

    inference_session_id: str
    call_id: str


@dataclasses.dataclass(frozen=True)
class ClaimResult:
    """The outcome of an atomic claim attempt."""

    outcome: ClaimOutcome
    result: ToolExecutionResult | None = None  # set on ALREADY_COMPLETED (replay)
    lease_id: str | None = None
    lease_owner: str | None = None
    reason: str = ""


@serializable
@dataclasses.dataclass(frozen=True)
class ToolExecutionRecord:
    """A persisted execution record (safe metadata only)."""

    inference_session_id: str
    call_id: str
    tool_name: str
    arguments_hash: str
    project_id: str
    session_id: str
    task_id: str | None
    run_id: str | None
    state: ToolExecutionState
    execution_semantics: ToolExecutionSemantics
    permission: str
    lease_id: str | None
    lease_owner: str | None
    lease_expires_at: float | None
    attempt: int
    started_at: str | None
    completed_at: str | None
    result: ToolExecutionResult | None
    error: str | None
    heartbeat_at: float | None = None
    heartbeat_count: int = 0


def _status_to_state(status: ToolExecutionStatus) -> ToolExecutionState:
    return {
        ToolExecutionStatus.SUCCEEDED: ToolExecutionState.SUCCEEDED,
        ToolExecutionStatus.FAILED: ToolExecutionState.FAILED,
        ToolExecutionStatus.DENIED: ToolExecutionState.DENIED,
        ToolExecutionStatus.INVALID_ARGUMENTS: ToolExecutionState.INVALID_ARGUMENTS,
        ToolExecutionStatus.TIMEOUT: ToolExecutionState.TIMEOUT,
        ToolExecutionStatus.UNAVAILABLE: ToolExecutionState.FAILED,
        ToolExecutionStatus.RESOURCE_LIMIT: ToolExecutionState.RESOURCE_LIMIT,
        ToolExecutionStatus.CANCELLED: ToolExecutionState.CANCELLED,
        ToolExecutionStatus.UNKNOWN: ToolExecutionState.UNKNOWN,
    }[status]


def _state_to_status(state: ToolExecutionState) -> ToolExecutionStatus:
    return {
        ToolExecutionState.SUCCEEDED: ToolExecutionStatus.SUCCEEDED,
        ToolExecutionState.FAILED: ToolExecutionStatus.FAILED,
        ToolExecutionState.DENIED: ToolExecutionStatus.DENIED,
        ToolExecutionState.INVALID_ARGUMENTS: ToolExecutionStatus.INVALID_ARGUMENTS,
        ToolExecutionState.TIMEOUT: ToolExecutionStatus.TIMEOUT,
        ToolExecutionState.RESOURCE_LIMIT: ToolExecutionStatus.RESOURCE_LIMIT,
        ToolExecutionState.CANCELLED: ToolExecutionStatus.CANCELLED,
        ToolExecutionState.UNKNOWN: ToolExecutionStatus.UNKNOWN,
    }.get(state, ToolExecutionStatus.UNKNOWN)


@runtime_checkable
class ToolExecutionStore(Protocol):
    """A durable, lease-based tool-execution store (Phase 9.4).

    ``claim`` is atomic: two concurrent callers can never both receive
    ownership of the same ``(inference_session_id, call_id)``. Terminal results
    are replayed; active claims expose their lease; stale claims are detectable
    and recoverable only per tool-execution semantics.
    """

    def claim(
        self,
        identity: ToolExecutionIdentity,
        *,
        tool_name: str,
        arguments_hash: str,
        project_id: str,
        session_id: str,
        task_id: str | None,
        run_id: str | None,
        execution_semantics: ToolExecutionSemantics,
        permission: str,
        lease_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> ClaimResult: ...

    def mark_running(self, identity: ToolExecutionIdentity, lease_id: str) -> None: ...

    def heartbeat(
        self, identity: ToolExecutionIdentity, lease_id: str, lease_duration_seconds: float
    ) -> None: ...

    def complete(
        self, identity: ToolExecutionIdentity, lease_id: str, result: ToolExecutionResult
    ) -> None: ...

    def release(self, identity: ToolExecutionIdentity, lease_id: str) -> None: ...

    def reclaim(
        self,
        identity: ToolExecutionIdentity,
        *,
        lease_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> ClaimResult: ...

    def mark_unknown(self, identity: ToolExecutionIdentity, reason: str) -> None: ...

    def inspect(self, identity: ToolExecutionIdentity) -> ToolExecutionRecord | None: ...

    def is_stale(self, identity: ToolExecutionIdentity) -> bool: ...


def _conflict_reason(
    record: dict[str, Any], tool_name: str, arguments_hash: str, project_id: str
) -> str | None:
    """Detect call-id reuse with different tool/arguments/scope.

    Empty stored values (e.g. legacy-migrated records that lacked the original
    argument hash or project) are treated as "unknown" and do **not** trigger a
    conflict — the tool name is still authoritative where known.
    """
    if record.get("tool_name") and record["tool_name"] != tool_name:
        return "call id reused with a different tool"
    if record.get("arguments_hash") and record["arguments_hash"] != arguments_hash:
        return "call id reused with different arguments"
    if record.get("project_id") and record["project_id"] != project_id:
        return "call id reused with a different project scope"
    return None


class SqliteToolExecutionStore:
    """SQLite-backed execution store with atomic claims and lease ownership.

    Claims use ``BEGIN IMMEDIATE`` (short transaction) and the
    ``PRIMARY KEY (inference_session_id, call_id)`` constraint; the database
    transaction is never held open during actual tool execution — the lease
    provides ownership during the long-running work.
    """

    _SCHEMA_VERSION = 2

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
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
            self._connections.append(conn)
        return conn

    def initialize(self) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS tool_execution_meta (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS tool_execution_records (
                    inference_session_id TEXT NOT NULL,
                    call_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_hash TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    task_id TEXT,
                    run_id TEXT,
                    state TEXT NOT NULL,
                    execution_semantics TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    lease_id TEXT,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    heartbeat_at REAL,
                    heartbeat_count INTEGER NOT NULL DEFAULT 0,
                    attempt INTEGER NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result_json TEXT,
                    error TEXT,
                    PRIMARY KEY (inference_session_id, call_id)
                )"""
            )
            db.execute(
                "INSERT OR REPLACE INTO tool_execution_meta (key, value) "
                "VALUES ('schema_version', ?)",
                (str(self._SCHEMA_VERSION),),
            )
            self._migrate_heartbeat_columns(db)
            self._migrate_legacy(db)

    def _migrate_heartbeat_columns(self, db: sqlite3.Connection) -> None:
        """Add heartbeat columns to a Phase 9.4 (v1) table, idempotently."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(tool_execution_records)")}
        if "heartbeat_at" not in columns:
            db.execute("ALTER TABLE tool_execution_records ADD COLUMN heartbeat_at REAL")
        if "heartbeat_count" not in columns:
            db.execute(
                "ALTER TABLE tool_execution_records "
                "ADD COLUMN heartbeat_count INTEGER NOT NULL DEFAULT 0"
            )

    def _migrate_legacy(self, db: sqlite3.Connection) -> None:
        """Migrate the Phase 9.3 ``tool_executions`` cache, preserving results."""
        has_legacy = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_executions'"
        ).fetchone()
        if has_legacy is None:
            return
        rows = db.execute(
            "SELECT inference_session_id, call_id, data FROM tool_executions"
        ).fetchall()
        for row in rows:
            result = loads(row["data"])
            if not isinstance(result, ToolExecutionResult):
                continue
            state = _status_to_state(result.status)
            db.execute(
                """INSERT OR IGNORE INTO tool_execution_records
                   (inference_session_id, call_id, tool_name, arguments_hash,
                    project_id, session_id, state, execution_semantics, permission,
                    lease_id, lease_owner, lease_expires_at, attempt,
                    completed_at, result_json, error)
                   VALUES (?, ?, ?, '', '', '', ?, ?, '', NULL, NULL, NULL, 1, ?, ?, NULL)""",
                (
                    row["inference_session_id"],
                    row["call_id"],
                    result.tool_name,
                    state.value,
                    ToolExecutionSemantics.UNKNOWN.value,
                    None,
                    dumps(result),
                ),
            )
        db.execute("DROP TABLE tool_executions")

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

    # -- protocol ---------------------------------------------------------

    def claim(
        self,
        identity: ToolExecutionIdentity,
        *,
        tool_name: str,
        arguments_hash: str,
        project_id: str,
        session_id: str,
        task_id: str | None,
        run_id: str | None,
        execution_semantics: ToolExecutionSemantics,
        permission: str,
        lease_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> ClaimResult:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM tool_execution_records "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (identity.inference_session_id, identity.call_id),
                ).fetchone()
                if row is None:
                    self._insert(
                        db,
                        identity,
                        tool_name=tool_name,
                        arguments_hash=arguments_hash,
                        project_id=project_id,
                        session_id=session_id,
                        task_id=task_id,
                        run_id=run_id,
                        state=ToolExecutionState.CLAIMED,
                        execution_semantics=execution_semantics,
                        permission=permission,
                        lease_id=lease_id,
                        lease_owner=lease_owner,
                        lease_expires_at=time.time() + lease_duration_seconds,
                        attempt=1,
                    )
                    db.execute("COMMIT")
                    return ClaimResult(
                        ClaimOutcome.CLAIMED, lease_id=lease_id, lease_owner=lease_owner
                    )

                record = self._record_from_row(row)
                conflict = _conflict_reason(
                    dict(row), tool_name, arguments_hash, project_id
                )
                if conflict is not None:
                    db.execute("COMMIT")
                    return ClaimResult(ClaimOutcome.CONFLICT, reason=conflict)

                if record.state in _TERMINAL_STATES:
                    db.execute("COMMIT")
                    return ClaimResult(ClaimOutcome.ALREADY_COMPLETED, result=record.result)

                # PENDING: released/available → claim it.
                if record.state is ToolExecutionState.PENDING:
                    self._update_lease(
                        db, identity, lease_id, lease_owner, lease_duration_seconds
                    )
                    self._increment_attempt(db, identity)
                    db.execute("COMMIT")
                    return ClaimResult(
                        ClaimOutcome.CLAIMED, lease_id=lease_id, lease_owner=lease_owner
                    )

                # CLAIMED / RUNNING: active lease.
                if _is_expired(record.lease_expires_at):
                    db.execute("COMMIT")
                    return ClaimResult(ClaimOutcome.STALE, reason="stale lease")
                db.execute("COMMIT")
                return ClaimResult(
                    ClaimOutcome.ALREADY_CLAIMED,
                    lease_id=record.lease_id,
                    lease_owner=record.lease_owner,
                )
            except Exception:
                db.execute("ROLLBACK")
                raise

    def reclaim(
        self,
        identity: ToolExecutionIdentity,
        *,
        lease_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> ClaimResult:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT * FROM tool_execution_records "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (identity.inference_session_id, identity.call_id),
                ).fetchone()
                if row is None:
                    db.execute("COMMIT")
                    return ClaimResult(ClaimOutcome.ALREADY_CLAIMED, reason="no record")
                record = self._record_from_row(row)
                if record.state in _TERMINAL_STATES:
                    db.execute("COMMIT")
                    return ClaimResult(ClaimOutcome.ALREADY_COMPLETED, result=record.result)
                if (
                    record.state in (ToolExecutionState.CLAIMED, ToolExecutionState.RUNNING)
                    and not _is_expired(record.lease_expires_at)
                ):
                    db.execute("COMMIT")
                    return ClaimResult(
                        ClaimOutcome.ALREADY_CLAIMED,
                        lease_id=record.lease_id,
                        lease_owner=record.lease_owner,
                        )
                self._update_lease(db, identity, lease_id, lease_owner, lease_duration_seconds)
                self._increment_attempt(db, identity)
                db.execute("COMMIT")
                return ClaimResult(
                    ClaimOutcome.CLAIMED, lease_id=lease_id, lease_owner=lease_owner
                )
            except Exception:
                db.execute("ROLLBACK")
                raise

    def mark_running(self, identity: ToolExecutionIdentity, lease_id: str) -> None:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._require_owned(db, identity, lease_id)
                db.execute(
                    "UPDATE tool_execution_records SET state = ?, started_at = ? "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (
                        ToolExecutionState.RUNNING.value,
                        _now_iso(),
                        identity.inference_session_id,
                        identity.call_id,
                    ),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def heartbeat(
        self, identity: ToolExecutionIdentity, lease_id: str, lease_duration_seconds: float
    ) -> None:
        """Renew the lease from *now* (short transaction; conditional update).

        Raises :class:`LeaseOwnershipError` unless exactly one active row owned
        by ``lease_id`` was extended — a lost/expired/terminal lease is never
        resurrected.
        """
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                cursor = db.execute(
                    "UPDATE tool_execution_records SET lease_expires_at = ?, "
                    "heartbeat_at = ?, heartbeat_count = heartbeat_count + 1 "
                    "WHERE inference_session_id = ? AND call_id = ? "
                    "AND lease_id = ? AND state IN ('CLAIMED', 'RUNNING')",
                    (
                        time.time() + lease_duration_seconds,
                        time.time(),
                        identity.inference_session_id,
                        identity.call_id,
                        lease_id,
                    ),
                )
                if cursor.rowcount != 1:
                    db.execute("ROLLBACK")
                    raise LeaseOwnershipError(
                        "heartbeat failed: lease not owned, expired, or terminal"
                    )
                db.execute("COMMIT")
            except LeaseOwnershipError:
                raise
            except Exception:
                db.execute("ROLLBACK")
                raise

    def complete(
        self, identity: ToolExecutionIdentity, lease_id: str, result: ToolExecutionResult
    ) -> None:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._require_owned(db, identity, lease_id)
                state = _status_to_state(result.status)
                db.execute(
                    "UPDATE tool_execution_records SET state = ?, completed_at = ?, "
                    "result_json = ?, error = ? "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (
                        state.value,
                        _now_iso(),
                        dumps(result),
                        result.error.message if result.error else None,
                        identity.inference_session_id,
                        identity.call_id,
                    ),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def release(self, identity: ToolExecutionIdentity, lease_id: str) -> None:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                self._require_owned(db, identity, lease_id)
                db.execute(
                    "UPDATE tool_execution_records SET state = ?, lease_id = NULL, "
                    "lease_owner = NULL, lease_expires_at = NULL "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (
                        ToolExecutionState.PENDING.value,
                        identity.inference_session_id,
                        identity.call_id,
                    ),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def mark_unknown(self, identity: ToolExecutionIdentity, reason: str) -> None:
        db = self._db()
        with self._write_lock:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "UPDATE tool_execution_records SET state = ?, completed_at = ?, error = ? "
                    "WHERE inference_session_id = ? AND call_id = ?",
                    (
                        ToolExecutionState.UNKNOWN.value,
                        _now_iso(),
                        reason,
                        identity.inference_session_id,
                        identity.call_id,
                    ),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def inspect(self, identity: ToolExecutionIdentity) -> ToolExecutionRecord | None:
        row = self._db().execute(
            "SELECT * FROM tool_execution_records "
            "WHERE inference_session_id = ? AND call_id = ?",
            (identity.inference_session_id, identity.call_id),
        ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def is_stale(self, identity: ToolExecutionIdentity) -> bool:
        record = self.inspect(identity)
        if record is None or record.state not in (
            ToolExecutionState.CLAIMED,
            ToolExecutionState.RUNNING,
        ):
            return False
        return _is_expired(record.lease_expires_at)

    # -- internals --------------------------------------------------------

    def _require_owned(
        self, db: sqlite3.Connection, identity: ToolExecutionIdentity, lease_id: str
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM tool_execution_records "
            "WHERE inference_session_id = ? AND call_id = ?",
            (identity.inference_session_id, identity.call_id),
        ).fetchone()
        if row is None:
            raise LeaseOwnershipError("no execution record to operate on")
        if row["lease_id"] != lease_id:
            raise LeaseOwnershipError("lease not owned by caller")
        if _is_expired(row["lease_expires_at"]):
            raise LeaseOwnershipError("lease has expired")
        return row  # type: ignore[no-any-return]

    def _insert(
        self,
        db: sqlite3.Connection,
        identity: ToolExecutionIdentity,
        **fields: Any,
    ) -> None:
        db.execute(
            """INSERT INTO tool_execution_records
               (inference_session_id, call_id, tool_name, arguments_hash,
                project_id, session_id, task_id, run_id, state,
                execution_semantics, permission, lease_id, lease_owner,
                lease_expires_at, attempt, started_at, completed_at,
                result_json, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)""",
            (
                identity.inference_session_id,
                identity.call_id,
                fields["tool_name"],
                fields["arguments_hash"],
                fields["project_id"],
                fields["session_id"],
                fields["task_id"],
                fields["run_id"],
                fields["state"].value,
                fields["execution_semantics"].value,
                fields["permission"],
                fields["lease_id"],
                fields["lease_owner"],
                fields["lease_expires_at"],
                fields["attempt"],
            ),
        )

    def _update_lease(
        self,
        db: sqlite3.Connection,
        identity: ToolExecutionIdentity,
        lease_id: str,
        lease_owner: str,
        lease_duration_seconds: float,
    ) -> None:
        db.execute(
            "UPDATE tool_execution_records SET state = ?, lease_id = ?, lease_owner = ?, "
            "lease_expires_at = ? WHERE inference_session_id = ? AND call_id = ?",
            (
                ToolExecutionState.CLAIMED.value,
                lease_id,
                lease_owner,
                time.time() + lease_duration_seconds,
                identity.inference_session_id,
                identity.call_id,
            ),
        )

    def _increment_attempt(self, db: sqlite3.Connection, identity: ToolExecutionIdentity) -> None:
        db.execute(
            "UPDATE tool_execution_records SET attempt = attempt + 1 "
            "WHERE inference_session_id = ? AND call_id = ?",
            (identity.inference_session_id, identity.call_id),
        )

    def _record_from_row(self, row: sqlite3.Row) -> ToolExecutionRecord:
        result = loads(row["result_json"]) if row["result_json"] else None
        return ToolExecutionRecord(
            inference_session_id=row["inference_session_id"],
            call_id=row["call_id"],
            tool_name=row["tool_name"],
            arguments_hash=row["arguments_hash"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            task_id=row["task_id"],
            run_id=row["run_id"],
            state=ToolExecutionState(row["state"]),
            execution_semantics=ToolExecutionSemantics(row["execution_semantics"]),
            permission=row["permission"],
            lease_id=row["lease_id"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            heartbeat_at=row["heartbeat_at"],
            heartbeat_count=row["heartbeat_count"],
            attempt=row["attempt"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=result if isinstance(result, ToolExecutionResult) else None,
            error=row["error"],
        )


class InMemoryToolExecutionStore:
    """Thread-safe in-memory execution store (tests and short-lived sessions)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def _key(self, identity: ToolExecutionIdentity) -> tuple[str, str]:
        return (identity.inference_session_id, identity.call_id)

    def initialize(self) -> None:
        return None

    def close(self) -> None:
        self._records.clear()

    def __enter__(self) -> InMemoryToolExecutionStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def claim(self, identity: ToolExecutionIdentity, **fields: Any) -> ClaimResult:
        with self._lock:
            key = self._key(identity)
            rec = self._records.get(key)
            if rec is None:
                self._records[key] = {
                    "tool_name": fields["tool_name"],
                    "arguments_hash": fields["arguments_hash"],
                    "project_id": fields["project_id"],
                    "session_id": fields["session_id"],
                    "task_id": fields["task_id"],
                    "run_id": fields["run_id"],
                    "state": ToolExecutionState.CLAIMED,
                    "execution_semantics": fields["execution_semantics"],
                    "permission": fields["permission"],
                    "lease_id": fields["lease_id"],
                    "lease_owner": fields["lease_owner"],
                    "lease_expires_at": time.time() + fields["lease_duration_seconds"],
                    "attempt": 1,
                    "result": None,
                    "error": None,
                }
                return ClaimResult(
                    ClaimOutcome.CLAIMED,
                    lease_id=fields["lease_id"],
                    lease_owner=fields["lease_owner"],
                )
            conflict = _conflict_reason(
                rec, fields["tool_name"], fields["arguments_hash"], fields["project_id"]
            )
            if conflict is not None:
                return ClaimResult(ClaimOutcome.CONFLICT, reason=conflict)
            state = rec["state"]
            if state in _TERMINAL_STATES:
                return ClaimResult(ClaimOutcome.ALREADY_COMPLETED, result=rec["result"])
            if state is ToolExecutionState.PENDING:
                rec.update(
                    state=ToolExecutionState.CLAIMED,
                    lease_id=fields["lease_id"],
                    lease_owner=fields["lease_owner"],
                    lease_expires_at=time.time() + fields["lease_duration_seconds"],
                )
                rec["attempt"] += 1
                return ClaimResult(
                    ClaimOutcome.CLAIMED,
                    lease_id=fields["lease_id"],
                    lease_owner=fields["lease_owner"],
                )
            if _is_expired(rec["lease_expires_at"]):
                return ClaimResult(ClaimOutcome.STALE, reason="stale lease")
            return ClaimResult(
                ClaimOutcome.ALREADY_CLAIMED,
                lease_id=rec["lease_id"],
                lease_owner=rec["lease_owner"],
            )

    def reclaim(self, identity: ToolExecutionIdentity, **fields: Any) -> ClaimResult:
        with self._lock:
            key = self._key(identity)
            rec = self._records.get(key)
            if rec is None:
                return ClaimResult(ClaimOutcome.ALREADY_CLAIMED, reason="no record")
            if rec["state"] in _TERMINAL_STATES:
                return ClaimResult(ClaimOutcome.ALREADY_COMPLETED, result=rec["result"])
            if (
                rec["state"] in (ToolExecutionState.CLAIMED, ToolExecutionState.RUNNING)
                and not _is_expired(rec["lease_expires_at"])
            ):
                return ClaimResult(
                    ClaimOutcome.ALREADY_CLAIMED,
                    lease_id=rec["lease_id"],
                        lease_owner=rec["lease_owner"],
                    )
            rec.update(
                state=ToolExecutionState.CLAIMED,
                lease_id=fields["lease_id"],
                lease_owner=fields["lease_owner"],
                lease_expires_at=time.time() + fields["lease_duration_seconds"],
            )
            rec["attempt"] += 1
            return ClaimResult(
                ClaimOutcome.CLAIMED, lease_id=fields["lease_id"], lease_owner=fields["lease_owner"]
            )

    def mark_running(self, identity: ToolExecutionIdentity, lease_id: str) -> None:
        rec = self._owned(identity, lease_id)
        rec["state"] = ToolExecutionState.RUNNING

    def heartbeat(
        self, identity: ToolExecutionIdentity, lease_id: str, lease_duration_seconds: float
    ) -> None:
        rec = self._owned(identity, lease_id)
        if rec["state"] not in (ToolExecutionState.CLAIMED, ToolExecutionState.RUNNING):
            raise LeaseOwnershipError("heartbeat failed: lease is not active")
        rec["lease_expires_at"] = time.time() + lease_duration_seconds
        rec["heartbeat_at"] = time.time()
        rec["heartbeat_count"] = rec.get("heartbeat_count", 0) + 1

    def complete(
        self, identity: ToolExecutionIdentity, lease_id: str, result: ToolExecutionResult
    ) -> None:
        rec = self._owned(identity, lease_id)
        rec["state"] = _status_to_state(result.status)
        rec["result"] = result
        rec["error"] = result.error.message if result.error else None

    def release(self, identity: ToolExecutionIdentity, lease_id: str) -> None:
        rec = self._owned(identity, lease_id)
        rec["state"] = ToolExecutionState.PENDING
        rec["lease_id"] = None
        rec["lease_owner"] = None
        rec["lease_expires_at"] = None

    def mark_unknown(self, identity: ToolExecutionIdentity, reason: str) -> None:
        with self._lock:
            rec = self._records.get(self._key(identity))
            if rec is None:
                return
            rec["state"] = ToolExecutionState.UNKNOWN
            rec["error"] = reason

    def inspect(self, identity: ToolExecutionIdentity) -> ToolExecutionRecord | None:
        with self._lock:
            rec = self._records.get(self._key(identity))
            if rec is None:
                return None
            return ToolExecutionRecord(
                inference_session_id=identity.inference_session_id,
                call_id=identity.call_id,
                tool_name=rec["tool_name"],
                arguments_hash=rec["arguments_hash"],
                project_id=rec["project_id"],
                session_id=rec["session_id"],
                task_id=rec["task_id"],
                run_id=rec["run_id"],
                state=rec["state"],
                execution_semantics=rec["execution_semantics"],
                permission=rec["permission"],
                lease_id=rec["lease_id"],
                lease_owner=rec["lease_owner"],
                lease_expires_at=rec["lease_expires_at"],
                heartbeat_at=rec.get("heartbeat_at"),
                heartbeat_count=rec.get("heartbeat_count", 0),
                attempt=rec["attempt"],
                started_at=None,
                completed_at=None,
                result=rec["result"],
                error=rec["error"],
            )

    def is_stale(self, identity: ToolExecutionIdentity) -> bool:
        record = self.inspect(identity)
        if record is None or record.state not in (
            ToolExecutionState.CLAIMED,
            ToolExecutionState.RUNNING,
        ):
            return False
        return _is_expired(record.lease_expires_at)

    def _owned(self, identity: ToolExecutionIdentity, lease_id: str) -> dict[str, Any]:
        with self._lock:
            rec = self._records.get(self._key(identity))
            if rec is None:
                raise LeaseOwnershipError("no execution record to operate on")
            if rec["lease_id"] != lease_id:
                raise LeaseOwnershipError("lease not owned by caller")
            if _is_expired(rec["lease_expires_at"]):
                raise LeaseOwnershipError("lease has expired")
            return rec


def _is_expired(lease_expires_at: float | None) -> bool:
    return lease_expires_at is not None and lease_expires_at < time.time()


def _now_iso() -> str:
    from qwen_research.common.timestamps import utc_now

    return utc_now().isoformat()


class LeaseHealth(StrEnum):
    """Liveness of an execution lease (internal; never exposed to the model)."""

    ALIVE = "alive"
    LOST = "lost"


class LeaseHeartbeat:
    """A lightweight local heartbeat controller for a long-running execution.

    Spawns a daemon thread that renews the lease at ``heartbeat_interval``
    (monotonic clock for scheduling; wall-clock UTC for persisted timestamps).
    A bounded retry tolerates transient SQLite contention; after that the lease
    is ``LOST`` and the owning execution transaction is notified via
    ``on_failure`` (it must not keep assuming ownership).

    The heartbeat thread only renews lease ownership/expiration — it never
    touches tool results, arguments, or execution state. ``stop()`` signals and
    joins the worker with a bounded timeout so no orphan thread survives.
    """

    def __init__(
        self,
        store: ToolExecutionStore,
        identity: ToolExecutionIdentity,
        lease_id: str,
        *,
        lease_duration_seconds: float,
        heartbeat_interval_seconds: float,
        retries: int = 3,
        retry_backoff_seconds: float = 0.05,
        on_failure: Callable[[str], None] | None = None,
    ) -> None:
        self._store = store
        self._identity = identity
        self._lease_id = lease_id
        self._lease_duration = lease_duration_seconds
        self._interval = heartbeat_interval_seconds
        self._retries = retries
        self._backoff = retry_backoff_seconds
        self._on_failure = on_failure
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._health = LeaseHealth.ALIVE
        self.heartbeat_count = 0
        self.heartbeat_failures = 0

    @property
    def lost(self) -> bool:
        with self._lock:
            return self._health is LeaseHealth.LOST

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="lease-heartbeat")
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        # Monotonic scheduling: system clock adjustments do not disrupt the loop.
        next_beat = time.monotonic() + self._interval
        while not self._stop.is_set():
            delay = next_beat - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
                if self._stop.is_set():
                    return
            if not self._heartbeat_once():
                return
            next_beat = time.monotonic() + self._interval

    def _heartbeat_once(self) -> bool:
        for attempt in range(self._retries):
            try:
                self._store.heartbeat(self._identity, self._lease_id, self._lease_duration)
                with self._lock:
                    self.heartbeat_count += 1
                return True
            except LeaseOwnershipError:
                break  # ownership lost — no point retrying
            except Exception:  # noqa: BLE001 — transient DB contention
                with self._lock:
                    self.heartbeat_failures += 1
                if attempt < self._retries - 1:
                    time.sleep(self._backoff * (2 ** attempt))
        self._mark_lost("heartbeat renewal failed")
        return False

    def _mark_lost(self, reason: str) -> None:
        with self._lock:
            if self._health is not LeaseHealth.LOST:
                self._health = LeaseHealth.LOST
        if self._on_failure is not None:
            self._on_failure(reason)
