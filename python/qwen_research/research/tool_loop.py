"""Controlled model ↔ Research Runtime tool-calling loop (Phase 9).

The provider only performs model inference; the Research Runtime owns tool
authorization, execution, continuation, loop limits, state, permissions, and
workflow accounting. This module implements that boundary: a bounded loop that
feeds model-generated ``ToolCall``s through the internal tool registry and
continues the same inference session with normalized tool results.

Invariants enforced here:

- Every tool call is **authorized** before execution (exists, model-callable,
  permission allowed, allow-listed, arguments valid against the schema).
- Tool calls execute **through the internal registry** (application APIs), never
  through the provider and never via raw filesystem/SQL/subprocess.
- Trusted scope (project/session/task/run) is **injected by the runtime**, never
  taken from the model's arguments.
- Hidden reasoning (``reasoning_content``) is carried only in ephemeral runtime
  state; it is never persisted (the serializer drops ``transient`` fields).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from qwen_research.common.ids import TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.domain.errors import PermissionError, StructuredOutputError
from qwen_research.domain.inference import (
    InferenceRequest,
    InferenceResult,
    Message,
    MessageRole,
    ToolCall,
)
from qwen_research.inference.schema_validation import validate_against_schema
from qwen_research.tools.base import ToolPermission
from qwen_research.tools.base import ToolResult as NeutralToolResult
from qwen_research.tools.registry import ToolRegistry, UnknownToolError


class ToolExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    INVALID_ARGUMENTS = "invalid_arguments"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class ToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT = "resource_limit"
    INTERNAL_ERROR = "internal_error"


class LoopStatus(StrEnum):
    FINAL = "final"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    TIME_LIMIT = "time_limit"
    CONTEXT_LIMIT = "context_limit"
    PERMISSION_DENIED = "permission_denied"
    PROVIDER_ERROR = "provider_error"
    TOOL_ERROR = "tool_error"


class ToolLoopEvent(StrEnum):
    INFERENCE_STARTED = "inference_started"
    INFERENCE_COMPLETED = "inference_completed"
    TOOL_REQUESTED = "tool_requested"
    TOOL_AUTHORIZED = "tool_authorized"
    TOOL_DENIED = "tool_denied"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    CONTINUATION_STARTED = "continuation_started"
    CONTINUATION_COMPLETED = "continuation_completed"
    LOOP_LIMIT = "loop_limit"


@serializable
@dataclasses.dataclass(frozen=True)
class ToolError:
    """A provider-neutral, model-visible tool error (no paths/stack/creds)."""

    code: ToolErrorCode
    message: str
    retryable: bool = False


@serializable
@dataclasses.dataclass(frozen=True)
class ToolExecutionRequest:
    """A tool execution the Research Runtime is about to authorize.

    ``call_id``/``tool_name``/``arguments`` may originate from the model;
    ``project_id``/``session_id``/``task_id``/``run_id`` are **trusted context**
    injected by the runtime (never taken from the model).
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    project_id: str
    session_id: str
    task_id: str | None = None
    run_id: str | None = None


@serializable
@dataclasses.dataclass(frozen=True)
class ToolExecutionResult:
    """The structured outcome of executing one tool call."""

    call_id: str
    tool_name: str
    status: ToolExecutionStatus
    content: str = ""
    structured_data: dict[str, Any] | None = None
    error: ToolError | None = None
    duration_ms: float | None = None
    provenance: dict[str, str] = dataclasses.field(default_factory=dict)


@serializable
@dataclasses.dataclass(frozen=True)
class ToolExecutionProfile:
    """The set of tools/permissions a task is allowed to hand to the model."""

    name: str
    allowed_permissions: frozenset[ToolPermission]
    allowed_tools: frozenset[str]
    parallel: bool = False
    max_calls: int = 16
    max_same_call: int = 2


@serializable
@dataclasses.dataclass(frozen=True)
class ToolLoopConfig:
    """Hard limits for a tool-call loop (no infinite loops)."""

    max_turns: int = 8
    max_tool_calls: int = 32
    max_total_tool_duration_ms: float = 60_000.0
    max_total_wall_time_ms: float = 120_000.0
    max_output_tokens: int = 16_384
    max_context_size: int = 64_000


@serializable
@dataclasses.dataclass
class LoopAccounting:
    """Aggregated loop accounting (mutable during the loop; frozen on return)."""

    inference_calls: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    tool_denials: int = 0
    loop_turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0


@serializable
@dataclasses.dataclass(frozen=True)
class InferenceSession:
    """Stable identity for a gateway-owned inference session (safe metadata)."""

    inference_session_id: str
    task_id: TaskId
    provider: str
    model: str
    mode: str
    created_at: str

    @classmethod
    def create(
        cls, *, task_id: TaskId, provider: str, model: str, mode: str
    ) -> InferenceSession:
        return cls(
            inference_session_id=new_id("inf_session"),
            task_id=task_id,
            provider=provider,
            model=model,
            mode=mode,
            created_at=utc_now().isoformat(),
        )


@dataclasses.dataclass
class InferenceConversation:
    """Ephemeral conversation state (reasoning_content is transient)."""

    invocation_id: str
    messages: list[Message]
    turn_count: int = 0
    token_usage: dict[str, int] = dataclasses.field(default_factory=dict)
    continuation_count: int = 0
    started_at: str = ""


@serializable
@dataclasses.dataclass(frozen=True)
class ToolLoopResult:
    """The outcome of a controlled tool-call loop."""

    status: LoopStatus
    final_result: InferenceResult | None = None
    session: InferenceSession | None = None
    accounting: LoopAccounting = dataclasses.field(default_factory=LoopAccounting)
    tool_results: tuple[ToolExecutionResult, ...] = ()
    error: str | None = None


#: Built-in tool-execution profiles.
READ_ONLY = ToolExecutionProfile(
    name="READ_ONLY",
    allowed_permissions=frozenset({ToolPermission.READ}),
    allowed_tools=frozenset(
        {
            "get_session",
            "get_task_state",
            "get_research_state",
            "search_corpus",
            "get_source",
            "get_project_memory",
            "get_research_memory",
            "get_open_questions",
            "get_verification_report",
            "get_contradictions",
            "describe_dataset",
            "get_computation_result",
        }
    ),
)

ANALYSIS = ToolExecutionProfile(
    name="ANALYSIS",
    allowed_permissions=frozenset({ToolPermission.READ, ToolPermission.ANALYZE}),
    allowed_tools=READ_ONLY.allowed_tools | frozenset({"run_query", "run_analysis"}),
)

RESEARCH = ToolExecutionProfile(
    name="RESEARCH",
    allowed_permissions=frozenset(
        {ToolPermission.READ, ToolPermission.ANALYZE, ToolPermission.WRITE}
    ),
    allowed_tools=ANALYSIS.allowed_tools | frozenset({"save_research_memory"}),
)

#: Default model tool profile (READ + ANALYZE, no WRITE/EXECUTE/DESTRUCTIVE).
DEFAULT_MODEL_PROFILE = ANALYSIS


def default_model_profile() -> ToolExecutionProfile:
    return DEFAULT_MODEL_PROFILE


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> ToolError | None:
    """Validate tool arguments against the tool's JSON Schema (shared validator)."""
    try:
        validate_against_schema(arguments, schema)
        return None
    except StructuredOutputError as exc:
        return ToolError(ToolErrorCode.INVALID_ARGUMENTS, str(exc))


def _tool_spec_for_tool(tool: Any) -> Any:
    from qwen_research.domain.inference import ToolSpec

    return ToolSpec(name=tool.name, description=tool.description, parameters=tool.schema)


def _model_callable_tools(
    registry: ToolRegistry, profile: ToolExecutionProfile
) -> list[Any]:
    return [
        registry.get(name)
        for name in profile.allowed_tools
        if name in registry and getattr(registry.get(name), "model_callable", True)
    ]


def _serialize_content(
    data: dict[str, Any], *, limit: int = 4000
) -> tuple[str, dict[str, Any] | None]:
    """Serialize tool output into a bounded model-visible content string."""
    try:
        text = json.dumps(data, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(data)
    if len(text) > limit:
        text = text[:limit] + f"\n…(truncated, {len(text)} chars total)"
    return text, data


def run_tool_loop(
    request: InferenceRequest,
    *,
    invoke: Callable[[InferenceRequest], InferenceResult],
    tools: ToolRegistry,
    profile: ToolExecutionProfile,
    config: ToolLoopConfig | None = None,
    project_id: str = "default",
    session_id: str = "",
    task_id: str | None = None,
    run_id: str | None = None,
    events: list[str] | None = None,
) -> ToolLoopResult:
    """Run the controlled model ↔ tool loop until a final answer or a limit.

    ``invoke`` performs one inference call (normally the Research Runtime's
    ``invoke_inference``). ``tools`` is the internal tool registry; ``profile``
    gates which tools/permissions are model-callable. Returns a
    :class:`ToolLoopResult` with the final :class:`InferenceResult` or a
    non-final status.
    """
    config = config or ToolLoopConfig()
    accounting = LoopAccounting()
    session = InferenceSession.create(
        task_id=request.task_reference,
        provider="qwen",
        model=request.inference_policy.model_requirement or "",
        mode="GATEWAY_INFERENCE",
    )
    conversation = InferenceConversation(
        invocation_id=new_id("invocation"),
        messages=list(request.messages),
        started_at=utc_now().isoformat(),
    )
    if not conversation.messages and request.context:
        conversation.messages.append(
            Message(role=MessageRole.USER, content="\n\n".join(request.context))
        )

    callable_tools = _model_callable_tools(tools, profile)
    tool_specs = tuple(_tool_spec_for_tool(t) for t in callable_tools)
    started = time.monotonic()
    results: list[ToolExecutionResult] = []
    same_call_counts: dict[str, int] = {}

    def _emit(event: str) -> None:
        if events is not None:
            events.append(event)

    while accounting.loop_turns < config.max_turns:
        accounting.loop_turns += 1
        _emit(ToolLoopEvent.INFERENCE_STARTED)
        req = dataclasses.replace(
            request,
            messages=tuple(conversation.messages),
            tools=tool_specs,
        )
        result = invoke(req)
        accounting.inference_calls += 1
        usage = result.usage or {}
        accounting.input_tokens += usage.get("input_tokens", 0)
        accounting.output_tokens += usage.get("output_tokens", 0)
        _emit(ToolLoopEvent.INFERENCE_COMPLETED)

        if not result.tool_calls_structured:
            return ToolLoopResult(
                status=LoopStatus.FINAL,
                final_result=result,
                session=session,
                accounting=dataclasses.replace(
                    accounting, duration_ms=(time.monotonic() - started) * 1000
                ),
                tool_results=tuple(results),
            )

        # Preserve the assistant's tool-call message (with transient reasoning).
        assistant = Message(
            role=MessageRole.ASSISTANT,
            content=result.content or "",
            tool_calls=result.tool_calls_structured,
            reasoning_content=result.reasoning_content,
        )
        conversation.messages.append(assistant)
        conversation.continuation_count += 1
        _emit(ToolLoopEvent.CONTINUATION_STARTED)

        for call in result.tool_calls_structured:
            if accounting.tool_calls >= config.max_tool_calls:
                _emit(ToolLoopEvent.LOOP_LIMIT)
                return ToolLoopResult(
                    status=LoopStatus.TOOL_LOOP_LIMIT,
                    session=session,
                    accounting=dataclasses.replace(
                        accounting, duration_ms=(time.monotonic() - started) * 1000
                    ),
                    tool_results=tuple(results),
                    error="max tool calls exceeded",
                )

            executed = _authorize_and_execute(
                call,
                tools=tools,
                profile=profile,
                project_id=project_id,
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                same_call_counts=same_call_counts,
                config=config,
                emit=_emit,
            )
            accounting.tool_calls += 1
            if executed.status in (
                ToolExecutionStatus.FAILED,
                ToolExecutionStatus.UNAVAILABLE,
                ToolExecutionStatus.TIMEOUT,
            ):
                accounting.tool_failures += 1
            if executed.status is ToolExecutionStatus.DENIED:
                accounting.tool_denials += 1
            results.append(executed)

            # Append the normalized tool-result message.
            content, structured = _serialize_content(
                {
                    "status": executed.status.value,
                    "content": executed.content,
                    "error": (
                        {"code": executed.error.code.value, "message": executed.error.message}
                        if executed.error
                        else None
                    ),
                }
            )
            conversation.messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=content,
                    tool_call_id=call.call_id,
                )
            )

        _emit(ToolLoopEvent.CONTINUATION_COMPLETED)

    _emit(ToolLoopEvent.LOOP_LIMIT)
    return ToolLoopResult(
        status=LoopStatus.TOOL_LOOP_LIMIT,
        session=session,
        accounting=dataclasses.replace(
            accounting, duration_ms=(time.monotonic() - started) * 1000
        ),
        tool_results=tuple(results),
        error="tool loop turn limit exceeded",
    )


def _authorize_and_execute(
    call: ToolCall,
    *,
    tools: ToolRegistry,
    profile: ToolExecutionProfile,
    project_id: str,
    session_id: str,
    task_id: str | None,
    run_id: str | None,
    same_call_counts: dict[str, int],
    config: ToolLoopConfig,
    emit: Callable[[str], None],
) -> ToolExecutionResult:
    """Authorize (6 checks) then execute one tool call, normalizing the outcome."""
    emit(ToolLoopEvent.TOOL_REQUESTED)

    # 1. tool exists
    try:
        tool = tools.get(call.tool_name)
    except UnknownToolError:
        emit(ToolLoopEvent.TOOL_DENIED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.DENIED,
            error=ToolError(ToolErrorCode.NOT_FOUND, "tool not found"),
        )

    # 2. tool is enabled (model-callable)
    if not getattr(tool, "model_callable", True):
        emit(ToolLoopEvent.TOOL_DENIED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.DENIED,
            error=ToolError(ToolErrorCode.PERMISSION_DENIED, "tool not model-callable"),
        )

    # 3. permission is allowed + 4. tool is allow-listed
    if (
        tool.permission not in profile.allowed_permissions
        or call.tool_name not in profile.allowed_tools
    ):
        emit(ToolLoopEvent.TOOL_DENIED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.DENIED,
            error=ToolError(ToolErrorCode.PERMISSION_DENIED, "tool not permitted"),
        )

    # 5. arguments validate against the tool schema (and were parseable)
    if call.arguments_error is not None:
        emit(ToolLoopEvent.TOOL_DENIED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.INVALID_ARGUMENTS,
            error=ToolError(ToolErrorCode.INVALID_ARGUMENTS, call.arguments_error),
        )
    validation_error = _validate_arguments(tool.schema, call.arguments)
    if validation_error is not None:
        emit(ToolLoopEvent.TOOL_DENIED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.INVALID_ARGUMENTS,
            error=validation_error,
        )

    # 6. repeated-tool guard (normalized signature)
    signature = _call_signature(call.tool_name, call.arguments)
    same_call_counts[signature] = same_call_counts.get(signature, 0) + 1
    if same_call_counts[signature] > profile.max_same_call:
        emit(ToolLoopEvent.LOOP_LIMIT)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.DENIED,
            error=ToolError(ToolErrorCode.RESOURCE_LIMIT, "repeated tool call limit exceeded"),
        )

    emit(ToolLoopEvent.TOOL_AUTHORIZED)
    emit(ToolLoopEvent.TOOL_STARTED)

    # Inject trusted scope; never trust the model's project/session.
    arguments = dict(call.arguments)
    arguments["project_id"] = project_id
    arguments["session_id"] = session_id
    if task_id is not None:
        arguments["task_id"] = task_id
    if run_id is not None:
        arguments["run_id"] = run_id

    tool_started = time.monotonic()
    try:
        neutral: NeutralToolResult = tool.execute(arguments)
    except PermissionError:
        emit(ToolLoopEvent.TOOL_FAILED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.DENIED,
            error=ToolError(ToolErrorCode.PERMISSION_DENIED, "permission denied"),
        )
    except Exception:  # noqa: BLE001 — normalize without leaking internals
        emit(ToolLoopEvent.TOOL_FAILED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.FAILED,
            error=ToolError(ToolErrorCode.INTERNAL_ERROR, "tool execution failed"),
        )
    duration_ms = (time.monotonic() - tool_started) * 1000

    if not neutral.ok:
        emit(ToolLoopEvent.TOOL_FAILED)
        return ToolExecutionResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolExecutionStatus.FAILED,
            content=neutral.error or "",
            error=ToolError(ToolErrorCode.INTERNAL_ERROR, neutral.error or "tool failed"),
            duration_ms=duration_ms,
        )

    emit(ToolLoopEvent.TOOL_COMPLETED)
    content, structured = _serialize_content(neutral.data)
    return ToolExecutionResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status=ToolExecutionStatus.SUCCEEDED,
        content=content,
        structured_data=structured,
        duration_ms=duration_ms,
        provenance={"tool": call.tool_name, "project_id": project_id},
    )


def _call_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{tool_name}:{canonical}".encode()).hexdigest()
    return digest
