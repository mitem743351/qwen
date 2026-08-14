"""ResearchContext verification-summary integration tests.

``build_research_context`` must include bounded verification summaries when a
verification service is configured, and none when it is not.
"""

from __future__ import annotations

from pathlib import Path

from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.memory.context import ContextBudget
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.verification.models import VerificationStatus
from verification_helpers import build_service, search_evidence


def test_build_research_context_includes_verification_summaries(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "surface code threshold")
    evidence = search_evidence(stack, "surface code threshold", limit=1)[0]
    service.link_claim_evidence("p", claim.claim_id, evidence, ClaimEvidenceRelationship.SUPPORTS)
    service.verify_claim("p", claim.claim_id)

    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"], verification=service)
    context = runtime.build_research_context("surface code", project_id="p")

    assert len(context.verification) == 1
    summary = context.verification[0]
    assert summary.claim_id == claim.claim_id
    assert summary.project_id == "p"
    assert summary.status is VerificationStatus.SUPPORTED
    assert summary.independent_corroboration is False
    assert summary.contradiction_count == 0


def test_verification_summaries_are_bounded(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"], verification=service)

    # Create + verify more claims than the budget allows.
    for i in range(ContextBudget().max_verification_summaries + 3):
        claim = service.create_claim("p", f"claim number {i}")
        service.verify_claim("p", claim.claim_id)

    context = runtime.build_research_context("anything", project_id="p")
    assert len(context.verification) == ContextBudget().max_verification_summaries


def test_no_verification_service_yields_no_summaries(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    # Runtime without a verification service.
    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"])
    context = runtime.build_research_context("anything", project_id="p")
    assert context.verification == ()
    # (Unused service kept for clarity that summaries come from the runtime's
    # configured verification service, not globally.)
    assert service is not None


def test_summary_reflects_corroboration(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    claim = service.create_claim("p", "quantum error correction")
    evidence = search_evidence(stack, "quantum error correction", limit=10)
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
        service.link_claim_evidence("p", claim.claim_id, e, ClaimEvidenceRelationship.SUPPORTS)
    service.verify_claim("p", claim.claim_id)

    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"], verification=service)
    context = runtime.build_research_context("quantum error correction", project_id="p")

    assert len(context.verification) == 1
    assert context.verification[0].independent_corroboration is True
