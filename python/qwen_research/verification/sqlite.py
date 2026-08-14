"""SQLite verification store.

A single local database holds claims, claim–evidence links, evidence
assessments, contradictions, verification reports, and source-quality records.
SQL is confined here; schema versioning is minimal (rebuildable cache, like the
corpus index).
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from qwen_research.claims.models import (
    Claim,
    ClaimStatus,
    ClaimType,
)
from qwen_research.claims.relationships import (
    ClaimEvidenceLink,
    ClaimEvidenceRelationship,
    LinkStatus,
)
from qwen_research.common.serialization import dumps, loads
from qwen_research.contradictions.models import (
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    ContradictionType,
)
from qwen_research.sources.quality import SourceQuality, SourceTier
from qwen_research.verification.models import (
    EvidenceAssessment,
    Severity,
    VerificationIssue,
    VerificationReport,
    VerificationScope,
    VerificationStatus,
)

_SCHEMA_VERSION = 1

_SCHEMA_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS verification_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS claims (
        claim_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        text TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence REAL,
        source_refs TEXT NOT NULL,
        evidence_refs TEXT NOT NULL,
        supporting_refs TEXT NOT NULL,
        contradicting_refs TEXT NOT NULL,
        scope TEXT,
        quantitative TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_claims_project ON claims (project_id)",
    """
    CREATE TABLE IF NOT EXISTS claim_evidence_links (
        link_id TEXT PRIMARY KEY,
        claim_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        relationship TEXT NOT NULL,
        rationale TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_links_claim ON claim_evidence_links (claim_id)",
    """
    CREATE TABLE IF NOT EXISTS evidence_assessments (
        assessment_id TEXT PRIMARY KEY,
        claim_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        support_type TEXT NOT NULL,
        rationale TEXT NOT NULL,
        status TEXT NOT NULL,
        quality TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_assessments_claim ON evidence_assessments (claim_id)",
    """
    CREATE TABLE IF NOT EXISTS contradictions (
        contradiction_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        claim_a TEXT NOT NULL,
        claim_b TEXT NOT NULL,
        evidence_a TEXT,
        evidence_b TEXT,
        type TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        rationale TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contradictions_project ON contradictions (project_id)",
    """
    CREATE TABLE IF NOT EXISTS verification_reports (
        report_id TEXT PRIMARY KEY,
        scope TEXT NOT NULL,
        claim_id TEXT,
        project_id TEXT NOT NULL,
        status TEXT NOT NULL,
        issues TEXT NOT NULL,
        evidence TEXT NOT NULL,
        contradictions TEXT NOT NULL,
        source_assessments TEXT NOT NULL,
        coverage TEXT NOT NULL,
        generated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reports_project ON verification_reports (project_id)",
    """
    CREATE TABLE IF NOT EXISTS source_quality (
        source_id TEXT PRIMARY KEY,
        tier TEXT NOT NULL,
        authority TEXT,
        primary_source INTEGER NOT NULL,
        peer_reviewed INTEGER NOT NULL,
        recency TEXT,
        provenance_completeness TEXT NOT NULL,
        extraction_quality TEXT NOT NULL,
        notes TEXT NOT NULL
    )
    """,
)


class SqliteVerificationStore:
    """SQLite implementation of :class:`VerificationStore`."""

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
                "INSERT OR REPLACE INTO verification_meta (key, value) "
                "VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        for conn in self._connections:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        self._connections.clear()

    def __enter__(self) -> SqliteVerificationStore:
        self.initialize()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- claims ------------------------------------------------------------

    def save_claim(self, claim: Claim) -> None:
        self.update_claim(claim)

    def update_claim(self, claim: Claim) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO claims
                    (claim_id, project_id, text, type, status, confidence,
                     source_refs, evidence_refs, supporting_refs, contradicting_refs,
                     scope, quantitative, created_at, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim.claim_id,
                    claim.project_id,
                    claim.text,
                    claim.type.value,
                    claim.status.value,
                    claim.confidence,
                    json.dumps(claim.source_refs),
                    json.dumps(claim.evidence_refs),
                    json.dumps(claim.supporting_refs),
                    json.dumps(claim.contradicting_refs),
                    dumps(claim.scope) if claim.scope is not None else None,
                    dumps(claim.quantitative) if claim.quantitative is not None else None,
                    claim.created_at.isoformat(),
                    claim.updated_at.isoformat(),
                    claim.version,
                ),
            )

    def get_claim(self, project_id: str, claim_id: str) -> Claim | None:
        row = self._db().execute(
            "SELECT * FROM claims WHERE project_id = ? AND claim_id = ?",
            (project_id, claim_id),
        ).fetchone()
        return _claim_from_row(row) if row else None

    def get_claims(self, project_id: str) -> list[Claim]:
        rows = self._db().execute(
            "SELECT * FROM claims WHERE project_id = ? ORDER BY created_at", (project_id,)
        ).fetchall()
        return [_claim_from_row(r) for r in rows]

    # -- claim-evidence links ---------------------------------------------

    def save_link(self, link: ClaimEvidenceLink) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO claim_evidence_links
                    (link_id, claim_id, evidence_id, relationship, rationale, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    link.link_id,
                    link.claim_id,
                    link.evidence_id,
                    link.relationship.value,
                    link.rationale,
                    link.status.value,
                    link.created_at.isoformat(),
                ),
            )

    def get_links(self, claim_id: str) -> list[ClaimEvidenceLink]:
        rows = self._db().execute(
            "SELECT * FROM claim_evidence_links WHERE claim_id = ? ORDER BY created_at",
            (claim_id,),
        ).fetchall()
        return [
            ClaimEvidenceLink(
                link_id=r["link_id"],
                claim_id=r["claim_id"],
                evidence_id=r["evidence_id"],
                relationship=ClaimEvidenceRelationship(r["relationship"]),
                rationale=r["rationale"],
                status=LinkStatus(r["status"]),
                created_at=_parse(r["created_at"]),
            )
            for r in rows
        ]

    # -- evidence assessments ---------------------------------------------

    def save_assessment(self, assessment: EvidenceAssessment) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO evidence_assessments
                    (assessment_id, claim_id, evidence_id, support_type, rationale,
                     status, quality, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.assessment_id,
                    assessment.claim_id,
                    assessment.evidence_id,
                    assessment.support_type.value,
                    assessment.rationale,
                    assessment.status.value,
                    dumps(assessment.quality),
                    assessment.created_at.isoformat(),
                ),
            )

    def get_assessments(self, claim_id: str) -> list[EvidenceAssessment]:
        rows = self._db().execute(
            "SELECT * FROM evidence_assessments WHERE claim_id = ? ORDER BY created_at",
            (claim_id,),
        ).fetchall()
        return [
            EvidenceAssessment(
                assessment_id=r["assessment_id"],
                claim_id=r["claim_id"],
                evidence_id=r["evidence_id"],
                support_type=__import__(
                    "qwen_research.evidence.models", fromlist=["SupportType"]
                ).SupportType(r["support_type"]),
                rationale=r["rationale"],
                status=VerificationStatus(r["status"]),
                quality=loads(r["quality"]),
                created_at=_parse(r["created_at"]),
            )
            for r in rows
        ]

    # -- contradictions ----------------------------------------------------

    def save_contradiction(self, contradiction: Contradiction) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO contradictions
                    (contradiction_id, project_id, claim_a, claim_b, evidence_a,
                     evidence_b, type, severity, status, rationale, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contradiction.contradiction_id,
                    contradiction.project_id,
                    contradiction.claim_a,
                    contradiction.claim_b,
                    contradiction.evidence_a,
                    contradiction.evidence_b,
                    contradiction.type.value,
                    contradiction.severity.value,
                    contradiction.status.value,
                    contradiction.rationale,
                    contradiction.created_at.isoformat(),
                    contradiction.updated_at.isoformat(),
                ),
            )

    def get_contradictions(self, project_id: str) -> list[Contradiction]:
        rows = self._db().execute(
            "SELECT * FROM contradictions WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        ).fetchall()
        return [_contradiction_from_row(r) for r in rows]

    def get_contradictions_for_claim(self, claim_id: str) -> list[Contradiction]:
        rows = self._db().execute(
            "SELECT * FROM contradictions WHERE claim_a = ? OR claim_b = ? ORDER BY created_at",
            (claim_id, claim_id),
        ).fetchall()
        return [_contradiction_from_row(r) for r in rows]

    # -- verification reports ---------------------------------------------

    def save_report(self, report: VerificationReport) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO verification_reports
                    (report_id, scope, claim_id, project_id, status, issues, evidence,
                     contradictions, source_assessments, coverage, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.scope.value,
                    report.claim_id,
                    report.project_id,
                    report.status.value,
                    _dump_issues(report.issues),
                    json.dumps(report.evidence),
                    json.dumps(report.contradictions),
                    json.dumps(report.source_assessments),
                    dumps(report.coverage),
                    report.generated_at.isoformat(),
                ),
            )

    def get_report(self, project_id: str, report_id: str) -> VerificationReport | None:
        row = self._db().execute(
            "SELECT * FROM verification_reports WHERE project_id = ? AND report_id = ?",
            (project_id, report_id),
        ).fetchone()
        return _report_from_row(row) if row else None

    def get_reports(self, project_id: str) -> list[VerificationReport]:
        rows = self._db().execute(
            "SELECT * FROM verification_reports WHERE project_id = ? ORDER BY generated_at",
            (project_id,),
        ).fetchall()
        return [_report_from_row(r) for r in rows]

    # -- source quality ----------------------------------------------------

    def save_source_quality(self, source_id: str, quality: SourceQuality) -> None:
        db = self._db()
        with self._write_lock, db:
            db.execute(
                """
                INSERT OR REPLACE INTO source_quality
                    (source_id, tier, authority, primary_source, peer_reviewed, recency,
                     provenance_completeness, extraction_quality, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    quality.tier.value,
                    quality.authority,
                    int(quality.primary_source),
                    int(quality.peer_reviewed),
                    quality.recency,
                    quality.provenance_completeness,
                    quality.extraction_quality,
                    quality.notes,
                ),
            )

    def get_source_quality(self, source_id: str) -> SourceQuality | None:
        row = self._db().execute(
            "SELECT * FROM source_quality WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        return SourceQuality(
            tier=SourceTier(row["tier"]),
            authority=row["authority"],
            primary_source=bool(row["primary_source"]),
            peer_reviewed=bool(row["peer_reviewed"]),
            recency=row["recency"],
            provenance_completeness=row["provenance_completeness"],
            extraction_quality=row["extraction_quality"],
            notes=row["notes"],
        )


def _parse(value: str) -> datetime:
    from datetime import datetime

    return datetime.fromisoformat(value)


def _claim_from_row(row: sqlite3.Row) -> Claim:
    return Claim(
        claim_id=row["claim_id"],
        project_id=row["project_id"],
        text=row["text"],
        type=ClaimType(row["type"]),
        status=ClaimStatus(row["status"]),
        confidence=row["confidence"],
        source_refs=tuple(json.loads(row["source_refs"])),
        evidence_refs=tuple(json.loads(row["evidence_refs"])),
        supporting_refs=tuple(json.loads(row["supporting_refs"])),
        contradicting_refs=tuple(json.loads(row["contradicting_refs"])),
        scope=loads(row["scope"]) if row["scope"] else None,
        quantitative=loads(row["quantitative"]) if row["quantitative"] else None,
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
        version=row["version"],
    )


def _contradiction_from_row(row: sqlite3.Row) -> Contradiction:
    return Contradiction(
        contradiction_id=row["contradiction_id"],
        project_id=row["project_id"],
        claim_a=row["claim_a"],
        claim_b=row["claim_b"],
        evidence_a=row["evidence_a"],
        evidence_b=row["evidence_b"],
        type=ContradictionType(row["type"]),
        severity=ContradictionSeverity(row["severity"]),
        status=ContradictionStatus(row["status"]),
        rationale=row["rationale"],
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
    )


def _report_from_row(row: sqlite3.Row) -> VerificationReport:
    return VerificationReport(
        report_id=row["report_id"],
        scope=VerificationScope(row["scope"]),
        claim_id=row["claim_id"],
        project_id=row["project_id"],
        status=VerificationStatus(row["status"]),
        issues=_load_issues(row["issues"]),
        evidence=tuple(json.loads(row["evidence"])),
        contradictions=tuple(json.loads(row["contradictions"])),
        source_assessments=tuple(json.loads(row["source_assessments"])),
        coverage=loads(row["coverage"]),
        generated_at=_parse(row["generated_at"]),
    )


def _dump_issues(issues: tuple[VerificationIssue, ...]) -> str:
    return json.dumps(
        [
            {
                "code": i.code,
                "severity": i.severity.value,
                "entity_type": i.entity_type,
                "entity_id": i.entity_id,
                "message": i.message,
            }
            for i in issues
        ]
    )


def _load_issues(data: str) -> tuple[VerificationIssue, ...]:
    return tuple(
        VerificationIssue(
            code=x["code"],
            severity=Severity(x["severity"]),
            entity_type=x["entity_type"],
            entity_id=x["entity_id"],
            message=x["message"],
        )
        for x in json.loads(data)
    )
