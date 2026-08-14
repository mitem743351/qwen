"""Claim model and claim-service tests."""

from __future__ import annotations

from pathlib import Path

from qwen_research.claims.models import ClaimStatus, ClaimType, QuantitativeClaim, Scope
from qwen_research.domain.errors import ClaimNotFoundError
from verification_helpers import build_service


def test_create_claim_defaults_unreviewed(tmp_path: Path) -> None:
    service, store, _ = build_service(tmp_path)
    claim = service.create_claim("p1", "surface code threshold is ~1%")
    assert claim.status is ClaimStatus.UNREVIEWED
    assert claim.type is ClaimType.UNKNOWN
    assert claim.version == 1
    # Persisted.
    assert store.get_claim(claim.claim_id) is not None


def test_create_claim_with_type_and_scope(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path)
    claim = service.create_claim(
        "p1",
        "error rate below 1%",
        claim_type=ClaimType.QUANTITATIVE,
        scope=Scope(population="surface code", dataset="sim-1"),
        quantitative=QuantitativeClaim(
            metric="error_rate", value=1.0, unit="percent", operator="<"
        ),
    )
    assert claim.type is ClaimType.QUANTITATIVE
    assert claim.scope is not None
    assert claim.scope.population == "surface code"
    assert claim.quantitative is not None
    assert claim.quantitative.metric == "error_rate"


def test_claim_project_isolation(tmp_path: Path) -> None:
    service, store, _ = build_service(tmp_path)
    a = service.create_claim("projA", "claim in A")
    b = service.create_claim("projB", "claim in B")
    assert store.get_claims("projA") == [a]
    assert store.get_claims("projB") == [b]
    # Cross-project lookup by id still works (claim ids are unique), but listing
    # is project-scoped.
    loaded_b = store.get_claim(b.claim_id)
    assert loaded_b is not None
    assert loaded_b.project_id == "projB"


def test_claim_versioning(tmp_path: Path) -> None:
    service, store, _ = build_service(tmp_path)
    claim = service.create_claim("p", "text")
    updated = claim.with_status(ClaimStatus.ASSESSED)
    store.update_claim(updated)
    loaded = store.get_claim(claim.claim_id)
    assert loaded is not None
    assert loaded.status is ClaimStatus.ASSESSED
    assert loaded.version == 2


def test_get_claim_missing_raises(tmp_path: Path) -> None:
    import pytest

    service, _, _ = build_service(tmp_path)
    with pytest.raises(ClaimNotFoundError):
        service.get_claim("claim_missing")
