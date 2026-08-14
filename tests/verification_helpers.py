"""Helpers for Phase 5 verification tests."""

from __future__ import annotations

from pathlib import Path

from phase4_helpers import build_hybrid_stack
from qwen_research.claims.models import Claim, ClaimType, QuantitativeClaim, Scope
from qwen_research.verification.service import EvidenceIntegrityService
from qwen_research.verification.sqlite import SqliteVerificationStore


def build_service(
    tmp_path: Path,
) -> tuple[EvidenceIntegrityService, SqliteVerificationStore, dict]:
    """Build a verification service over the semantic fixture corpus."""
    stack = build_hybrid_stack(tmp_path)
    store = SqliteVerificationStore(tmp_path / "verification.db")
    store.initialize()
    service = EvidenceIntegrityService(store, corpus_index=stack["index"])
    return service, store, stack


def search_evidence(stack: dict, query: str, limit: int = 5) -> list[str]:
    """Return chunk ids from a hybrid search."""
    result = stack["hybrid"].search(query)
    return [c.chunk_id for c in result.chunks[:limit]]


def make_quantitative_claim(
    service: EvidenceIntegrityService,
    project_id: str,
    text: str,
    metric: str,
    value: float,
    unit: str,
    operator: str = "=",
    scope: Scope | None = None,
    time_range: str | None = None,
) -> Claim:
    return service.create_claim(
        project_id,
        text,
        claim_type=ClaimType.QUANTITATIVE,
        quantitative=QuantitativeClaim(
            metric=metric,
            value=value,
            unit=unit,
            operator=operator,
            time_range=time_range,
        ),
        scope=scope,
    )
