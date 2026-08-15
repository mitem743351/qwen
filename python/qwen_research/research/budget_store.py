"""Test-time budget persistence (Phase 10).

Restart-safe storage of a high-effort run's budget so a restart cannot reset
``consumed`` back to zero. Only safe budget metadata is persisted — no hidden
reasoning, no credentials, no raw tool payloads.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qwen_research.domain.test_time import TestTimeComputeBudget


@runtime_checkable
class BudgetStore(Protocol):
    def save(self, run_id: str, budget: TestTimeComputeBudget) -> None: ...

    def load(self, run_id: str) -> TestTimeComputeBudget | None: ...


class InMemoryBudgetStore:
    def __init__(self) -> None:
        self._budgets: dict[str, TestTimeComputeBudget] = {}

    def save(self, run_id: str, budget: TestTimeComputeBudget) -> None:
        self._budgets[run_id] = budget

    def load(self, run_id: str) -> TestTimeComputeBudget | None:
        return self._budgets.get(run_id)


class SqliteBudgetStore:
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
                """CREATE TABLE IF NOT EXISTS test_time_budgets (
                    run_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )"""
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteBudgetStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, run_id: str, budget: TestTimeComputeBudget) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO test_time_budgets (run_id, data) VALUES (?, ?)",
                (run_id, json.dumps(budget.to_record(), sort_keys=True)),
            )

    def load(self, run_id: str) -> TestTimeComputeBudget | None:
        row = self._db().execute(
            "SELECT data FROM test_time_budgets WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return record_to_budget(json.loads(row[0]))


def record_to_budget(record: dict[str, Any]) -> TestTimeComputeBudget:
    """Deserialize a budget record (see ``TestTimeComputeBudget.to_record``)."""
    return TestTimeComputeBudget.from_record(record)
