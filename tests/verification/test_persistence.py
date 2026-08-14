"""Verification persistence and restart tests."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_hybrid_stack
from qwen_research.claims.models import ClaimStatus, ClaimType, QuantitativeClaim
from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.verification.service import EvidenceIntegrityService
from qwen_research.verification.sqlite import SqliteVerificationStore
from verification_helpers import search_evidence


def test_full_stack_restart(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    db = tmp_path / "verification.db"

    # --- first process: create claim, link, verify ---
    store = SqliteVerificationStore(db)
    store.initialize()
    service = EvidenceIntegrityService(store, corpus_index=stack["index"])
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code threshold", limit=1)[0]
    service.link_claim_evidence("p", claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS)
    report = service.verify_claim("p", claim.claim_id)
    report_id = report.report_id
    store.close()

    # --- second process: reopen and reload (same corpus index) ---
    store2 = SqliteVerificationStore(db)
    store2.initialize()
    service2 = EvidenceIntegrityService(store2, corpus_index=stack["index"])

    loaded_claim = service2.get_claim("p", claim.claim_id)
    assert loaded_claim.status is ClaimStatus.SUPPORTED

    loaded_report = service2.get_verification_report("p", report_id)
    assert loaded_report.status.value == "supported"

    # A quantitative contradiction survives restart too.
    a = service2.create_claim(
        "p", "error < 1%", claim_type=ClaimType.QUANTITATIVE,
        quantitative=QuantitativeClaim(metric="error_rate", value=1.0, operator="<"),
    )
    b = service2.create_claim(
        "p", "error >= 5%", claim_type=ClaimType.QUANTITATIVE,
        quantitative=QuantitativeClaim(metric="error_rate", value=5.0, operator=">="),
    )
    contradictions = service2.get_contradictions("p")
    assert any(
        {c.claim_a, c.claim_b} == {a.claim_id, b.claim_id} for c in contradictions
    )


def test_schema_version(tmp_path: Path) -> None:
    import sqlite3

    store = SqliteVerificationStore(tmp_path / "v.db")
    store.initialize()
    conn = sqlite3.connect(tmp_path / "v.db")
    version = conn.execute(
        "SELECT value FROM verification_meta WHERE key='schema_version'"
    ).fetchone()[0]
    conn.close()
    assert version == "1"


def test_project_isolation_in_reports(tmp_path: Path) -> None:
    stack = build_hybrid_stack(tmp_path)
    store = SqliteVerificationStore(tmp_path / "v.db")
    store.initialize()
    service = EvidenceIntegrityService(store, corpus_index=stack["index"])
    a = service.create_claim("A", "claim A")
    b = service.create_claim("B", "claim B")
    service.verify_claim("A", a.claim_id)
    service.verify_claim("B", b.claim_id)
    assert {r.project_id for r in store.get_reports("A")} == {"A"}
    assert {r.project_id for r in store.get_reports("B")} == {"B"}
