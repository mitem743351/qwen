"""SQLite memory store.

A single local database holds structured memory in logically separate tables
(one per category). It is physically separate from the corpus index by default
(a distinct file), and SQL remains confined to this module.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from qwen_research.common.timestamps import utc_now
from qwen_research.memory.models import (
    DecisionRecord,
    MemoryOrigin,
    ProjectMemory,
    QuestionStatus,
    ResearchMemory,
    ResearchQuestion,
    SessionMemoryItem,
    SourceMemory,
)

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS memory_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_memory (
        memory_id    TEXT PRIMARY KEY,
        session_id   TEXT NOT NULL,
        project_id   TEXT NOT NULL,
        kind         TEXT NOT NULL,
        content_json TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        version      INTEGER NOT NULL,
        status       TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_memory (
        memory_id      TEXT PRIMARY KEY,
        project_id     TEXT NOT NULL,
        content        TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        origin         TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        version        INTEGER NOT NULL,
        status         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS research_memory (
        memory_id       TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        content         TEXT NOT NULL,
        source_refs     TEXT NOT NULL,
        evidence_refs   TEXT NOT NULL,
        claim_refs      TEXT NOT NULL,
        status          TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        origin          TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        version         INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id   TEXT PRIMARY KEY,
        project_id    TEXT NOT NULL,
        session_id    TEXT,
        decision      TEXT NOT NULL,
        reason        TEXT NOT NULL,
        evidence_refs TEXT NOT NULL,
        source_refs   TEXT NOT NULL,
        status        TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        version       INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS questions (
        question_id     TEXT PRIMARY KEY,
        project_id      TEXT NOT NULL,
        question        TEXT NOT NULL,
        priority        INTEGER NOT NULL,
        status          TEXT NOT NULL,
        related_claims  TEXT NOT NULL,
        related_sources TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        version         INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_memory (
        id                  INTEGER PRIMARY KEY,
        project_id          TEXT NOT NULL,
        source_id           TEXT NOT NULL,
        importance          TEXT,
        reliability_notes   TEXT,
        topics_json         TEXT NOT NULL,
        citation_json       TEXT NOT NULL,
        annotations_json    TEXT NOT NULL,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        version             INTEGER NOT NULL,
        UNIQUE (project_id, source_id)
    )
    """,
)

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_session_mem_session ON session_memory (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_project_mem_project ON project_memory (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_research_mem_project ON research_memory (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_questions_project ON questions (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_mem_project ON source_memory (project_id)",
)


def _now() -> str:
    return utc_now().isoformat()


class SqliteMemoryStore:
    """Implements all six memory repository protocols over SQLite."""

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
            for index in _INDEXES:
                db.execute(index)
            db.execute(
                "INSERT OR REPLACE INTO memory_meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteMemoryStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- session memory ----------------------------------------------------

    def save_session_item(self, item: SessionMemoryItem) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO session_memory "
                "(memory_id, session_id, project_id, kind, content_json, "
                " created_at, updated_at, version, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.memory_id, item.session_id, item.project_id, item.kind,
                    json.dumps(item.content, sort_keys=True),
                    item.created_at.isoformat(), item.updated_at.isoformat(),
                    item.version, item.status,
                ),
            )

    def get_session_items(self, session_id: str) -> list[SessionMemoryItem]:
        rows = self._db().execute(
            "SELECT * FROM session_memory WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [
            SessionMemoryItem(
                memory_id=r["memory_id"], session_id=r["session_id"], project_id=r["project_id"],
                kind=r["kind"], content=json.loads(r["content_json"]),
                created_at=_parse(r["created_at"]), updated_at=_parse(r["updated_at"]),
                version=r["version"], status=r["status"],
            )
            for r in rows
        ]

    # -- project memory ----------------------------------------------------

    def save_project_memory(self, memory: ProjectMemory) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO project_memory "
                "(memory_id, project_id, content, provenance_json, origin, "
                " created_at, updated_at, version, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    memory.memory_id, memory.project_id, memory.content,
                    json.dumps(memory.provenance, sort_keys=True), memory.origin.value,
                    memory.created_at.isoformat(), memory.updated_at.isoformat(),
                    memory.version, memory.status,
                ),
            )

    def get_project_memory(self, project_id: str) -> list[ProjectMemory]:
        rows = self._db().execute(
            "SELECT * FROM project_memory WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [
            ProjectMemory(
                memory_id=r["memory_id"], project_id=r["project_id"], content=r["content"],
                provenance=json.loads(r["provenance_json"]), origin=MemoryOrigin(r["origin"]),
                created_at=_parse(r["created_at"]), updated_at=_parse(r["updated_at"]),
                version=r["version"], status=r["status"],
            )
            for r in rows
        ]

    # -- research memory ---------------------------------------------------

    def save_research_memory(self, memory: ResearchMemory) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO research_memory "
                "(memory_id, project_id, content, source_refs, evidence_refs, claim_refs, "
                " status, provenance_json, origin, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    memory.memory_id, memory.project_id, memory.content,
                    json.dumps(memory.source_refs), json.dumps(memory.evidence_refs),
                    json.dumps(memory.claim_refs), memory.status,
                    json.dumps(memory.provenance, sort_keys=True), memory.origin.value,
                    memory.created_at.isoformat(), memory.updated_at.isoformat(),
                    memory.version,
                ),
            )

    def get_research_memory(self, project_id: str) -> list[ResearchMemory]:
        rows = self._db().execute(
            "SELECT * FROM research_memory WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [
            ResearchMemory(
                memory_id=r["memory_id"], project_id=r["project_id"], content=r["content"],
                source_refs=tuple(json.loads(r["source_refs"])),
                evidence_refs=tuple(json.loads(r["evidence_refs"])),
                claim_refs=tuple(json.loads(r["claim_refs"])),
                status=r["status"], provenance=json.loads(r["provenance_json"]),
                origin=MemoryOrigin(r["origin"]),
                created_at=_parse(r["created_at"]), updated_at=_parse(r["updated_at"]),
                version=r["version"],
            )
            for r in rows
        ]

    # -- decisions ---------------------------------------------------------

    def save_decision(self, decision: DecisionRecord) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO decisions "
                "(decision_id, project_id, session_id, decision, reason, evidence_refs, "
                " source_refs, status, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision.decision_id, decision.project_id, decision.session_id,
                    decision.decision, decision.reason,
                    json.dumps(decision.evidence_refs), json.dumps(decision.source_refs),
                    decision.status, decision.created_at.isoformat(),
                    decision.updated_at.isoformat(), decision.version,
                ),
            )

    def get_decisions(self, project_id: str) -> list[DecisionRecord]:
        rows = self._db().execute(
            "SELECT * FROM decisions WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [
            DecisionRecord(
                decision_id=r["decision_id"], project_id=r["project_id"],
                session_id=r["session_id"], decision=r["decision"], reason=r["reason"],
                evidence_refs=tuple(json.loads(r["evidence_refs"])),
                source_refs=tuple(json.loads(r["source_refs"])),
                status=r["status"], created_at=_parse(r["created_at"]),
                updated_at=_parse(r["updated_at"]), version=r["version"],
            )
            for r in rows
        ]

    # -- questions ---------------------------------------------------------

    def save_question(self, question: ResearchQuestion) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO questions "
                "(question_id, project_id, question, priority, status, related_claims, "
                " related_sources, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    question.question_id, question.project_id, question.question,
                    question.priority, question.status.value,
                    json.dumps(question.related_claims), json.dumps(question.related_sources),
                    question.created_at.isoformat(), question.updated_at.isoformat(),
                    question.version,
                ),
            )

    def update_question(self, question: ResearchQuestion) -> None:
        bumped = _bump_question(question)
        self.save_question(bumped)

    def get_questions(self, project_id: str) -> list[ResearchQuestion]:
        rows = self._db().execute(
            "SELECT * FROM questions WHERE project_id = ? ORDER BY priority DESC, created_at",
            (project_id,),
        ).fetchall()
        return [
            ResearchQuestion(
                question_id=r["question_id"], project_id=r["project_id"],
                question=r["question"], priority=r["priority"],
                status=QuestionStatus(r["status"]),
                related_claims=tuple(json.loads(r["related_claims"])),
                related_sources=tuple(json.loads(r["related_sources"])),
                created_at=_parse(r["created_at"]), updated_at=_parse(r["updated_at"]),
                version=r["version"],
            )
            for r in rows
        ]

    # -- source memory -----------------------------------------------------

    def save_source_memory(self, memory: SourceMemory) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                "INSERT OR REPLACE INTO source_memory "
                "(project_id, source_id, importance, reliability_notes, topics_json, "
                " citation_json, annotations_json, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    memory.project_id, memory.source_id, memory.importance,
                    memory.reliability_notes, json.dumps(memory.topics),
                    json.dumps(memory.citation_metadata, sort_keys=True),
                    json.dumps(memory.user_annotations, sort_keys=True),
                    memory.created_at.isoformat(), memory.updated_at.isoformat(),
                    memory.version,
                ),
            )

    def get_source_memory(
        self, project_id: str, source_id: str | None = None
    ) -> list[SourceMemory]:
        if source_id is not None:
            rows = self._db().execute(
                "SELECT * FROM source_memory WHERE project_id = ? AND source_id = ?",
                (project_id, source_id),
            ).fetchall()
        else:
            rows = self._db().execute(
                "SELECT * FROM source_memory WHERE project_id = ?", (project_id,)
            ).fetchall()
        return [
            SourceMemory(
                source_id=r["source_id"], project_id=r["project_id"],
                importance=r["importance"], reliability_notes=r["reliability_notes"],
                topics=tuple(json.loads(r["topics_json"])),
                citation_metadata=json.loads(r["citation_json"]),
                user_annotations=json.loads(r["annotations_json"]),
                created_at=_parse(r["created_at"]), updated_at=_parse(r["updated_at"]),
                version=r["version"],
            )
            for r in rows
        ]


def _bump_question(question: ResearchQuestion) -> ResearchQuestion:
    import dataclasses

    return dataclasses.replace(
        question, version=question.version + 1, updated_at=utc_now()
    )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)
