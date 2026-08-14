"""Claim–evidence linking and assessment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.domain.errors import ClaimNotFoundError, EvidenceNotFoundError
from qwen_research.evidence.models import SupportType
from verification_helpers import build_service, search_evidence


def test_link_supports(tmp_path: Path) -> None:
    service, store, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    link = service.link_claim_evidence(
        claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS, "direct"
    )
    assert link.relationship is ClaimEvidenceRelationship.SUPPORTS
    assert store.get_links(claim.claim_id) == [link]


def test_link_contradicts_and_qualifies(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "threshold")
    evidence = search_evidence(stack, "surface code", limit=3)
    service.link_claim_evidence(claim.claim_id, evidence[0], ClaimEvidenceRelationship.CONTRADICTS)
    service.link_claim_evidence(claim.claim_id, evidence[1], ClaimEvidenceRelationship.QUALIFIES)
    relationships = {link.relationship for link in service._store.get_links(claim.claim_id)}
    assert relationships == {
        ClaimEvidenceRelationship.CONTRADICTS,
        ClaimEvidenceRelationship.QUALIFIES,
    }


def test_link_invalid_evidence_raises(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path)
    claim = service.create_claim("p", "threshold")
    with pytest.raises(EvidenceNotFoundError):
        service.link_claim_evidence(
        claim.claim_id, "chunk_missing", ClaimEvidenceRelationship.SUPPORTS
    )


def test_link_missing_claim_raises(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    with pytest.raises(ClaimNotFoundError):
        service.link_claim_evidence("claim_missing", evidence, ClaimEvidenceRelationship.SUPPORTS)


def test_assess_evidence_maps_support_type(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "threshold")
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    service.link_claim_evidence(claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS)
    assessment = service.assess_evidence(claim.claim_id, evidence)
    assert assessment.support_type is SupportType.DIRECT_SUPPORT
    assert assessment.quality.source_quality is not None


def test_assess_evidence_without_link_is_unknown(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "threshold")
    evidence = search_evidence(stack, "surface code", limit=1)[0]
    assessment = service.assess_evidence(claim.claim_id, evidence)
    assert assessment.support_type is SupportType.UNKNOWN
