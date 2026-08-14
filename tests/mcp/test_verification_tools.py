"""MCP verification tool permissions and runtime integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.claims.models import ClaimType
from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.common.ids import ClaimId, EvidenceId
from qwen_research.domain.errors import UnsupportedOperationError
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, MCPPermission
from qwen_research.research.runtime import InMemoryResearchRuntime
from verification_helpers import build_service, search_evidence


def test_verification_tool_permissions() -> None:
    assert DEFAULT_TOOL_PERMISSIONS["create_claim"] is MCPPermission.WRITE
    assert DEFAULT_TOOL_PERMISSIONS["link_claim_evidence"] is MCPPermission.WRITE
    assert DEFAULT_TOOL_PERMISSIONS["assess_evidence"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["verify_claim"] is MCPPermission.ANALYZE
    assert DEFAULT_TOOL_PERMISSIONS["get_verification_report"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_contradictions"] is MCPPermission.READ


def test_runtime_verification_roundtrip(tmp_path: Path) -> None:
    service, _, stack = build_service(tmp_path)
    runtime = InMemoryResearchRuntime(retriever=stack["hybrid"], verification=service)

    claim = runtime.create_claim("p", "surface code threshold", claim_type=ClaimType.FACTUAL)
    evidence_id = EvidenceId(search_evidence(stack, "surface code threshold", limit=1)[0])
    runtime.link_claim_evidence(
        "p", claim.claim_id, evidence_id, ClaimEvidenceRelationship.SUPPORTS
    )
    runtime.assess_evidence("p", claim.claim_id, evidence_id)
    report = runtime.verify_claim("p", claim.claim_id)
    assert report.claim_id == claim.claim_id
    assert runtime.get_verification_report("p", report.report_id).report_id == report.report_id
    assert runtime.get_contradictions("p") == []


def test_runtime_verification_unavailable(tmp_path: Path) -> None:
    runtime = InMemoryResearchRuntime()
    with pytest.raises(UnsupportedOperationError):
        runtime.create_claim("p", "text")
    with pytest.raises(UnsupportedOperationError):
        runtime.verify_claim("p", ClaimId("claim_1"))
    with pytest.raises(UnsupportedOperationError):
        runtime.get_contradictions("p")
