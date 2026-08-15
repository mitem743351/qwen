"""Hybrid Studio/Gateway orchestration boundary (Phase 9 — contract only).

Phase 9 establishes the explicit abstract contract for hand-off between
STUDIO_NATIVE and GATEWAY_INFERENCE but does **not** implement automatic
escalation (that is Phase 10/11). This module defines the request/result value
objects and the transfer-validation rule that keeps secrets and hidden
reasoning out of the boundary.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum

from qwen_research.common.serialization import serializable


class EscalationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ALREADY_IN_TARGET_MODE = "already_in_target_mode"


@serializable
@dataclasses.dataclass(frozen=True)
class EscalationRequest:
    """A request to move a task between operating modes.

    ``context_refs`` are **references** (evidence/computation/memory/artifact
    ids), never raw content; ``tool_policy`` is the tool-execution profile name.
    """

    session_id: str
    task_id: str
    reason: str
    target_mode: str
    context_refs: tuple[str, ...] = ()
    tool_policy: str = "ANALYSIS"


@serializable
@dataclasses.dataclass(frozen=True)
class EscalationResult:
    """The outcome of an escalation decision (no automatic selector yet)."""

    status: EscalationStatus
    target_mode: str
    inference_ref: str = ""


#: Field names that may cross the Studio ↔ Gateway boundary.
_ALLOWED_TRANSFER_FIELDS = frozenset(
    {
        "session_id",
        "task_id",
        "reason",
        "target_mode",
        "context_refs",
        "tool_policy",
        "status",
        "inference_ref",
        "user_request",
        "evidence_refs",
        "memory_summaries",
        "computation_summaries",
        "workflow_state",
    }
)

#: Field names that must never cross the boundary.
_FORBIDDEN_TRANSFER_FIELDS = frozenset(
    {
        "api_key",
        "credential",
        "credentials",
        "reasoning_content",
        "hidden_reasoning",
        "secrets",
        "filesystem_path",
        "path",
        "token",
    }
)


def validate_transfer(fields: dict[str, object]) -> None:
    """Reject boundary transfers that would carry secrets or hidden reasoning.

    Raises :class:`ValueError` if any key is forbidden; silent on safe keys.
    """
    forbidden = sorted(_FORBIDDEN_TRANSFER_FIELDS & set(fields))
    if forbidden:
        raise ValueError(
            f"transfer fields not allowed across the hybrid boundary: {forbidden}"
        )
