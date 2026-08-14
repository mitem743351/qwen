"""Verification engine + service end-to-end tests."""

from __future__ import annotations

from pathlib import Path

from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.verification.models import VerificationStatus
from verification_helpers import build_service, search_evidence


def test_verify_no_evidence_is_insufficient(tmp_path: Path) -> None:
    service, store, _ = build_service(tmp_path)
    claim = service.create_claim("p", "threshold claim")
    report = service.verify_claim(claim.claim_id)
    assert report.status is VerificationStatus.INSUFFICIENT_EVIDENCE
    assert report.coverage.claims_with_evidence == 0
    # Report persisted.
    assert store.get_report(report.report_id) is not None


def test_verify_single_source_supported(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code threshold", limit=1)[0]
    service.link_claim_evidence(claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS)
    report = service.verify_claim(claim.claim_id)
    assert report.status is VerificationStatus.SUPPORTED
    assert report.coverage.claims_with_evidence == 1
    assert report.coverage.claims_with_independent_corroboration == 0


def test_verify_two_independent_sources_corroborated(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "quantum error correction")
    # Link evidence from two distinct documents.
    evidence = search_evidence(stack, "quantum error correction", limit=10)
    doc_ids = {stack["index"].get_chunks_for_ids([e])[0].document_id for e in evidence}
    assert len(doc_ids) >= 2, "need at least two distinct documents"
    picked = []
    seen_docs: set[str] = set()
    for e in evidence:
        doc = stack["index"].get_chunks_for_ids([e])[0].document_id
        if doc not in seen_docs:
            seen_docs.add(doc)
            picked.append(e)
        if len(picked) == 2:
            break
    for e in picked:
        service.link_claim_evidence(claim.claim_id, e, ClaimEvidenceRelationship.SUPPORTS)
    report = service.verify_claim(claim.claim_id)
    assert report.status is VerificationStatus.VERIFIED_WITHIN_CORPUS
    assert report.coverage.claims_with_independent_corroboration == 1


def test_verify_contradicting_evidence_contested(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code", limit=2)
    service.link_claim_evidence(claim.claim_id, evidence[0], ClaimEvidenceRelationship.SUPPORTS)
    service.link_claim_evidence(claim.claim_id, evidence[1], ClaimEvidenceRelationship.CONTRADICTS)
    report = service.verify_claim(claim.claim_id)
    assert report.status is VerificationStatus.CONTESTED


def test_verify_updates_claim_status(tmp_path: Path) -> None:
    from qwen_research.claims.models import ClaimStatus

    service, store, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code threshold", limit=1)[0]
    service.link_claim_evidence(claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS)
    service.verify_claim(claim.claim_id)
    updated = store.get_claim(claim.claim_id)
    assert updated is not None
    assert updated.status is ClaimStatus.SUPPORTED


def test_verify_missing_evidence_issue(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    # Link to a bogus evidence id is rejected at link time, so instead verify a
    # claim whose evidence was later removed from the corpus is hard to simulate;
    # here we verify the "no evidence" issue code appears.
    report = service.verify_claim(claim.claim_id)
    codes = {i.code for i in report.issues}
    assert "claim_has_no_evidence" in codes


def test_get_verification_report_missing_raises(tmp_path: Path) -> None:
    import pytest

    from qwen_research.domain.errors import VerificationReportNotFoundError

    service, _, _ = build_service(tmp_path)
    with pytest.raises(VerificationReportNotFoundError):
        service.get_verification_report("report_missing")
