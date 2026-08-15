"""Controlled tool-call loop tests (Phase 9)."""

from __future__ import annotations

import dataclasses
from typing import Any

from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import dumps
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    Message,
    MessageRole,
    ToolCall,
)
from qwen_research.research.tool_loop import (
    ANALYSIS,
    READ_ONLY,
    LoopStatus,
    ToolErrorCode,
    ToolExecutionStatus,
    ToolLoopConfig,
    ToolPermission,
    run_tool_loop,
)
from qwen_research.tools.base import ToolResult
from qwen_research.tools.registry import ToolRegistry


class StubTool:
    def __init__(
        self,
        name: str,
        permission: ToolPermission,
        *,
        schema: dict[str, Any] | None = None,
        model_callable: bool = True,
        output: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = f"stub {name}"
        self.schema = schema or {"type": "object", "properties": {}}
        self.permission = permission
        self.model_callable = model_callable
        self._output = output or {"ok": True}
        self.calls: list[dict[str, Any]] = []

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(arguments)
        return ToolResult.success(self._output)


def _search_tool() -> StubTool:
    return StubTool(
        "search_corpus",
        ToolPermission.READ,
        schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def _registry(*tools: Any) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _request() -> InferenceRequest:
    return InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(),
        messages=(Message(role=MessageRole.USER, content="question"),),
    )


def _result(
    *, content: str = "", tool_calls: tuple[ToolCall, ...] = (), reasoning: str = ""
) -> InferenceResult:
    return InferenceResult(
        status="ok",
        model="qwen3.7-max",
        content=content,
        tool_calls_structured=tool_calls,
        usage={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
        finish_reason="tool_calls" if tool_calls else "stop",
        provider="qwen",
        reasoning_content=reasoning,
    )


def _scripted_invoke(
    results: list[InferenceResult],
) -> tuple[Any, list[InferenceRequest]]:
    n = 0
    requests: list[InferenceRequest] = []

    def invoke(request: InferenceRequest) -> InferenceResult:
        nonlocal n
        requests.append(request)
        idx = min(n, len(results) - 1)
        n += 1
        return results[idx]

    return invoke, requests


def test_final_answer_without_tools() -> None:
    invoke, _ = _scripted_invoke([_result(content="final answer")])
    outcome = run_tool_loop(
        _request(), invoke=invoke, tools=_registry(_search_tool()), profile=ANALYSIS
    )
    assert outcome.status is LoopStatus.FINAL
    assert outcome.final_result is not None
    assert outcome.final_result.content == "final answer"
    assert outcome.accounting.inference_calls == 1
    assert outcome.accounting.tool_calls == 0


def test_single_tool_call_then_final() -> None:
    tool = _search_tool()
    call = ToolCall(
        call_id="call_1", tool_name="search_corpus", arguments={"query": "surface code"}
    )
    invoke, requests = _scripted_invoke(
        [_result(tool_calls=(call,), reasoning="hidden CoT"), _result(content="the answer")]
    )
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    assert outcome.status is LoopStatus.FINAL
    # Tool executed with trusted project scope injected.
    assert tool.calls == [
        {"query": "surface code", "project_id": "default", "session_id": ""}
    ]
    assert outcome.accounting.tool_calls == 1
    # Continuation carried the assistant tool-call message + transient reasoning.
    second_request = requests[1]
    roles = [m.role for m in second_request.messages]
    assert MessageRole.ASSISTANT in roles
    assert MessageRole.TOOL in roles
    assistant = next(m for m in second_request.messages if m.role is MessageRole.ASSISTANT)
    assert assistant.reasoning_content == "hidden CoT"


def test_multiple_sequential_tool_calls_preserve_order() -> None:
    tool = _search_tool()
    calls = (
        ToolCall(call_id="call_1", tool_name="search_corpus", arguments={"query": "a"}),
        ToolCall(call_id="call_2", tool_name="search_corpus", arguments={"query": "b"}),
    )
    invoke, _ = _scripted_invoke([_result(tool_calls=calls), _result(content="done")])
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    assert outcome.status is LoopStatus.FINAL
    assert [c["query"] for c in tool.calls] == ["a", "b"]
    assert outcome.accounting.tool_calls == 2
    # Call IDs are preserved in the results.
    assert [r.call_id for r in outcome.tool_results] == ["call_1", "call_2"]


def test_unknown_tool_denied() -> None:
    call = ToolCall(call_id="c", tool_name="ghost_tool", arguments={})
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)), _result(content="ok")])
    outcome = run_tool_loop(
        _request(), invoke=invoke, tools=_registry(_search_tool()), profile=ANALYSIS
    )
    assert outcome.accounting.tool_denials == 1
    assert outcome.tool_results[0].status is ToolExecutionStatus.DENIED
    assert outcome.tool_results[0].error is not None
    assert outcome.tool_results[0].error.code is ToolErrorCode.NOT_FOUND


def test_permission_denied_for_write_tool() -> None:
    write_tool = StubTool("save_research_memory", ToolPermission.WRITE)
    call = ToolCall(call_id="c", tool_name="save_research_memory", arguments={})
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)), _result(content="ok")])
    outcome = run_tool_loop(
        _request(), invoke=invoke, tools=_registry(write_tool), profile=READ_ONLY
    )
    assert outcome.tool_results[0].status is ToolExecutionStatus.DENIED
    assert outcome.tool_results[0].error is not None
    assert outcome.tool_results[0].error.code is ToolErrorCode.PERMISSION_DENIED
    assert write_tool.calls == []  # never executed


def test_invalid_arguments_rejected() -> None:
    tool = _search_tool()
    call = ToolCall(call_id="c", tool_name="search_corpus", arguments={"wrong": "field"})
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)), _result(content="ok")])
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    assert outcome.tool_results[0].status is ToolExecutionStatus.INVALID_ARGUMENTS
    assert outcome.tool_results[0].error is not None
    assert outcome.tool_results[0].error.code is ToolErrorCode.INVALID_ARGUMENTS
    assert tool.calls == []  # not executed


def test_repeated_call_guard() -> None:
    tool = _search_tool()
    calls = tuple(
        ToolCall(call_id=f"c{i}", tool_name="search_corpus", arguments={"query": "same"})
        for i in range(4)
    )
    invoke, _ = _scripted_invoke([_result(tool_calls=calls), _result(content="ok")])
    outcome = run_tool_loop(
        _request(),
        invoke=invoke,
        tools=_registry(tool),
        profile=dataclasses.replace(ANALYSIS, max_same_call=2),
    )
    # Only 2 identical calls allowed; the rest are denied with RESOURCE_LIMIT.
    assert len(tool.calls) == 2
    assert any(
        r.error is not None and r.error.code is ToolErrorCode.RESOURCE_LIMIT
        for r in outcome.tool_results
    )


def test_loop_turn_limit() -> None:
    tool = _search_tool()
    call = ToolCall(call_id="c", tool_name="search_corpus", arguments={"query": "x"})
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)) for _ in range(20)])
    outcome = run_tool_loop(
        _request(),
        invoke=invoke,
        tools=_registry(tool),
        profile=ANALYSIS,
        config=ToolLoopConfig(max_turns=3),
    )
    assert outcome.status is LoopStatus.TOOL_LOOP_LIMIT
    assert outcome.accounting.loop_turns == 3


def test_usage_aggregated_across_turns() -> None:
    tool = _search_tool()
    call = ToolCall(call_id="c", tool_name="search_corpus", arguments={"query": "x"})
    invoke, _ = _scripted_invoke(
        [_result(tool_calls=(call,)), _result(content="final")]
    )
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    assert outcome.accounting.inference_calls == 2
    assert outcome.accounting.input_tokens == 20
    assert outcome.accounting.output_tokens == 40


def test_reasoning_content_not_persisted() -> None:
    tool = _search_tool()
    call = ToolCall(call_id="c", tool_name="search_corpus", arguments={"query": "x"})
    invoke, _ = _scripted_invoke(
        [_result(tool_calls=(call,), reasoning="secret CoT"), _result(content="final")]
    )
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    # Transient reasoning carried in-memory on the continuation…
    assert outcome.final_result is not None
    # …but never serialized.
    assert "secret CoT" not in dumps(outcome.final_result)
    assert "secret CoT" not in dumps(outcome)


def test_model_cannot_choose_project_scope() -> None:
    tool = _search_tool()
    call = ToolCall(
        call_id="c",
        tool_name="search_corpus",
        arguments={"query": "x", "project_id": "attacker-project"},
    )
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)), _result(content="ok")])
    run_tool_loop(
        _request(),
        invoke=invoke,
        tools=_registry(tool),
        profile=ANALYSIS,
        project_id="trusted-project",
    )
    # The runtime injected the trusted project id, overriding the model's value.
    assert tool.calls[0]["project_id"] == "trusted-project"


# -- Phase 9.1 regression tests -------------------------------------------

def test_regression_tool_then_final_continues_loop() -> None:
    """inference #1 → tool call → tool execution → inference #2 → final answer."""
    tool = _search_tool()
    call = ToolCall(call_id="call_1", tool_name="search_corpus", arguments={"query": "q"})
    invoke, requests = _scripted_invoke(
        [_result(tool_calls=(call,)), _result(content="final answer")]
    )
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    # The loop continued after tool execution and produced a FINAL result.
    assert outcome.status is LoopStatus.FINAL
    assert outcome.final_result is not None
    assert outcome.final_result.content == "final answer"
    assert len(requests) == 2  # exactly two inference calls
    assert tool.calls == [{"query": "q", "project_id": "default", "session_id": ""}]
    assert outcome.accounting.tool_calls == 1


def test_regression_malformed_tool_json_never_executes() -> None:
    """A tool call whose arguments failed to parse must never execute."""
    tool = _search_tool()
    call = ToolCall(
        call_id="call_1",
        tool_name="search_corpus",
        arguments={},
        arguments_error="malformed tool arguments JSON",
    )
    invoke, _ = _scripted_invoke([_result(tool_calls=(call,)), _result(content="ok")])
    outcome = run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    assert outcome.tool_results[0].status is ToolExecutionStatus.INVALID_ARGUMENTS
    assert outcome.tool_results[0].error is not None
    assert outcome.tool_results[0].error.code is ToolErrorCode.INVALID_ARGUMENTS
    assert tool.calls == []  # never executed


def test_regression_model_receives_bounded_tool_result() -> None:
    """The model receives bounded tool-result content, not the full output."""
    tool = StubTool(
        "search_corpus",
        ToolPermission.READ,
        output={"huge": "x" * 200_000},
    )
    call = ToolCall(call_id="call_1", tool_name="search_corpus", arguments={"query": "q"})
    invoke, requests = _scripted_invoke(
        [_result(tool_calls=(call,)), _result(content="ok")]
    )
    run_tool_loop(_request(), invoke=invoke, tools=_registry(tool), profile=ANALYSIS)
    second = requests[1]
    tool_message = next(m for m in second.messages if m.role is MessageRole.TOOL)
    assert len(tool_message.content) < 5000
    assert "x" * 200_000 not in tool_message.content
