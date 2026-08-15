"""Hybrid Studio/Gateway boundary contract tests (Phase 9)."""

from __future__ import annotations

import pytest

from qwen_research.research.hybrid import (
    EscalationRequest,
    EscalationResult,
    EscalationStatus,
    validate_transfer,
)


def test_escalation_request_carries_refs_not_content() -> None:
    request = EscalationRequest(
        session_id="s1",
        task_id="t1",
        reason="needs deeper research",
        target_mode="gateway_inference",
        context_refs=("evidence_1", "computation_2"),
        tool_policy="ANALYSIS",
    )
    assert request.target_mode == "gateway_inference"
    assert request.context_refs == ("evidence_1", "computation_2")


def test_escalation_result_defaults() -> None:
    result = EscalationResult(status=EscalationStatus.ACCEPTED, target_mode="gateway_inference")
    assert result.status is EscalationStatus.ACCEPTED
    assert result.inference_ref == ""


def test_validate_transfer_allows_safe_fields() -> None:
    validate_transfer(
        {
            "session_id": "s1",
            "task_id": "t1",
            "evidence_refs": ("e1",),
            "memory_summaries": ("m1",),
            "tool_policy": "ANALYSIS",
        }
    )


def test_validate_transfer_rejects_secrets() -> None:
    with pytest.raises(ValueError):
        validate_transfer({"api_key": "sk-secret"})


def test_validate_transfer_rejects_hidden_reasoning() -> None:
    with pytest.raises(ValueError):
        validate_transfer({"reasoning_content": "hidden CoT"})
    with pytest.raises(ValueError):
        validate_transfer({"filesystem_path": "/etc/passwd"})
