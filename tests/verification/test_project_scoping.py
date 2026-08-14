"""Project-scoping regression tests for verification operations.

Every claim lookup / link / assess / verify / report operation is scoped to a
project: a claim (or report) id from project A must not resolve from project B.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.domain.errors import (
    ClaimNotFoundError,
    VerificationReportNotFoundError,
)
from verification_helpers import build_service, search_evidence


def test_verify_claim_wrong_project_raises(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path)
    claim = service.create_claim("projA", "surface code threshold")
    with pytest.raises(ClaimNotFoundError):
        service.verify_claim("projB", claim.claim_id)


def test_assess_evidence_wrong_project_raises(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("projA", "surface code threshold")
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    with pytest.raises(ClaimNotFoundError):
        service.assess_evidence("projB", claim.claim_id, evidence)


def test_get_verification_report_wrong_project_raises(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("projA", "surface code threshold")
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    service.link_claim_evidence(
        "projA", claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS
    )
    report = service.verify_claim("projA", claim.claim_id)
    # Same project resolves.
    assert service.get_verification_report("projA", report.report_id) is not None
    # A different project does not.
    with pytest.raises(VerificationReportNotFoundError):
        service.get_verification_report("projB", report.report_id)


def test_contradictions_stay_project_scoped(tmp_path: Path) -> None:
    from verification_helpers import make_quantitative_claim

    service, _, _ = build_service(tmp_path)
    make_quantitative_claim(service, "A", "err=1", "error_rate", 1.0, "percent")
    make_quantitative_claim(service, "A", "err=5", "error_rate", 5.0, "percent")
    assert len(service.get_contradictions("A")) == 1
    assert service.get_contradictions("B") == []
