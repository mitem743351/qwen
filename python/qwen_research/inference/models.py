"""Runtime-level inference models.

The pure provider-neutral value objects (``Message``, ``ToolCall``,
``StructuredOutputSpec``, ``FinishReason``, ``InferenceStreamEvent``) live in
``domain/inference.py``; this module adds the runtime/persistence-level models
and re-exports the domain objects for convenience.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import SessionId, TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.domain.inference import (
    FinishReason,
    InferenceStreamEvent,
    Message,
    MessageRole,
    ProviderCapabilities,
    StreamEventType,
    StructuredOutputSpec,
    ToolCall,
    ToolResult,
)

__all__ = [
    "FinishReason",
    "InferenceStatus",
    "InferenceStreamEvent",
    "InvocationMetadata",
    "Message",
    "MessageRole",
    "ProviderErrorStatus",
    "ProviderHealth",
    "StreamEventType",
    "StructuredOutputSpec",
    "ToolCall",
    "ToolResult",
]


class InferenceStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


class ProviderErrorStatus(StrEnum):
    """Normalized provider failure classes (never raw stack traces)."""

    RATE_LIMITED = "rate_limited"
    RETRYABLE = "retryable"
    QUOTA_EXCEEDED = "quota_exceeded"
    AUTH_FAILED = "auth_failed"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


@dataclasses.dataclass(frozen=True)
class ProviderHealth:
    """On-demand inference-provider diagnostic (no continuous pings)."""

    available: bool
    latency_ms: float | None = None
    last_error: str | None = None
    models_available: tuple[str, ...] = ()
    capabilities: ProviderCapabilities = dataclasses.field(
        default_factory=ProviderCapabilities
    )


@serializable
@dataclasses.dataclass(frozen=True)
class InvocationMetadata:
    """Persistent inference-invocation metadata (secrets/hidden reasoning excluded)."""

    invocation_id: str
    task_id: TaskId | None
    session_id: SessionId | None
    provider: str
    model: str
    profile: str
    status: str
    finish_reason: str
    usage: dict[str, int]
    capability_decisions: tuple[str, ...]
    retry_count: int
    started_at: datetime
    completed_at: datetime | None
    latency_ms: float | None = None
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        task_id: TaskId | None,
        session_id: SessionId | None,
        provider: str,
        model: str,
        profile: str,
    ) -> InvocationMetadata:
        now = utc_now()
        return cls(
            invocation_id=new_id("invocation"),
            task_id=task_id,
            session_id=session_id,
            provider=provider,
            model=model,
            profile=profile,
            status="running",
            finish_reason="",
            usage={},
            capability_decisions=(),
            retry_count=0,
            started_at=now,
            completed_at=None,
        )
