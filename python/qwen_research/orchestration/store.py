"""SQLite orchestration store.

Persists research tasks, plans, workflow runs, and events. Structured objects
are stored via the versioned serializer; SQL is confined here. Large raw
intermediate outputs are never persisted — only structured references.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from pathlib import Path

from qwen_research.common.serialization import dumps, loads
from qwen_research.orchestration.models import (
    ResearchPlan,
    ResearchTask,
    WorkflowEvent,
    WorkflowRun,
)

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS orchestration_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS research_tasks (
        task_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        task_type TEXT NOT NULL,
        complexity TEXT NOT NULL,
        reasoning_profile TEXT NOT NULL,
        status TEXT NOT NULL,
        plan_id TEXT,
        workflow_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_tasks_project ON research_tasks (project_id)",
    """CREATE TABLE IF NOT EXISTS research_plans (
        plan_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_plans_project ON research_plans (project_id)",
    """CREATE TABLE IF NOT EXISTS workflow_runs (
        run_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        current_stage TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_runs_project ON workflow_runs (project_id)",
    """CREATE TABLE IF NOT EXISTS workflow_events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        stage_id TEXT,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        data TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_events_run ON workflow_events (run_id)",
)


class OrchestrationStore:
    """SQLite implementation of orchestration persistence."""

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
                "INSERT OR REPLACE INTO orchestration_meta (key, value) "
                "VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> OrchestrationStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- tasks -------------------------------------------------------------

    def save_task(self, task: ResearchTask) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO research_tasks
                   (task_id, project_id, session_id, task_type, complexity,
                    reasoning_profile, status, plan_id, workflow_id,
                    created_at, updated_at, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.project_id, task.session_id,
                    task.task_type.value, task.complexity.value, task.reasoning_profile,
                    task.status, task.plan_id, task.workflow_id,
                    task.created_at.isoformat(), task.updated_at.isoformat(), dumps(task),
                ),
            )

    def get_task(self, task_id: str) -> ResearchTask | None:
        row = self._db().execute(
            "SELECT data FROM research_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return loads(row["data"]) if row else None

    def list_tasks(self, project_id: str) -> list[ResearchTask]:
        rows = self._db().execute(
            "SELECT data FROM research_tasks WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [loads(r["data"]) for r in rows]

    # -- plans -------------------------------------------------------------

    def save_plan(self, plan: ResearchPlan, *, project_id: str) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO research_plans
                   (plan_id, task_id, project_id, created_at, data)
                   VALUES (?, ?, ?, ?, ?)""",
                (plan.plan_id, plan.task_id, project_id, plan.created_at.isoformat(), dumps(plan)),
            )

    def get_plan(self, plan_id: str) -> ResearchPlan | None:
        row = self._db().execute(
            "SELECT data FROM research_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        return loads(row["data"]) if row else None

    # -- runs --------------------------------------------------------------

    def save_run(self, run: WorkflowRun) -> None:
        task = self.get_task(run.task_id)
        project_id = task.project_id if task is not None else ""
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO workflow_runs
                   (run_id, task_id, plan_id, project_id, status, current_stage,
                    created_at, updated_at, completed_at, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.run_id, run.task_id, run.plan_id, project_id,
                    run.status.value, run.current_stage,
                    run.created_at.isoformat(), run.updated_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    dumps(run),
                ),
            )

    def get_run(self, run_id: str) -> WorkflowRun | None:
        row = self._db().execute(
            "SELECT data FROM workflow_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return loads(row["data"]) if row else None

    def save_event(self, event: WorkflowEvent) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """INSERT OR REPLACE INTO workflow_events
                   (event_id, run_id, stage_id, event_type, status, timestamp, data)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id, event.run_id, event.stage_id,
                    event.event_type.value, event.status, event.timestamp.isoformat(), dumps(event),
                ),
            )

    def get_events(self, run_id: str) -> list[WorkflowEvent]:
        rows = self._db().execute(
            "SELECT data FROM workflow_events WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        ).fetchall()
        return [loads(r["data"]) for r in rows]
