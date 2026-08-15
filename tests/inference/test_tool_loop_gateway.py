"""End-to-end gateway tool-loop flow (fake Qwen provider, real retrieval)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from corpus_helpers import index_fixture
from inference_helpers import TransportResponse, completion_response, make_provider
from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import InferencePolicy, InferenceRequest
from qwen_research.inference.runtime import InferenceRuntime
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.tool_loop import LoopStatus, ToolExecutionStatus


def _scripted_provider(tmp_path: Path) -> tuple[Any, Any]:
    """A fake Qwen provider: turn 1 requests search_corpus, turn 2 answers."""

    def handler(url: str, headers: dict, body: dict, timeout: float) -> TransportResponse:
        messages = body["messages"]
        # If a tool result is already present, produce the final answer.
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if has_tool_result:
            return completion_response(
                "The corpus confirms the surface-code threshold.", finish_reason="stop"
            )
        return completion_response(
            "",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "search_corpus",
                        "arguments": '{"query": "surface code"}',
                    },
                }
            ],
        )

    return make_provider(handler)


def test_gateway_tool_loop_end_to_end(tmp_path: Path) -> None:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    provider, _ = _scripted_provider(tmp_path)
    inference = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model="qwen3.7-max"
    )
    runtime = InMemoryResearchRuntime(retriever=retriever, inference=inference)

    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(model_requirement="qwen3.7-max"),
        messages=(),
        context=("What is the surface-code threshold?",),
    )

    outcome = runtime.run_tool_loop(request, project_id="default", session_id="s1")

    assert outcome.status is LoopStatus.FINAL
    assert outcome.final_result is not None
    assert outcome.final_result.ok
    assert "threshold" in outcome.final_result.content
    # The tool executed through the internal registry and succeeded.
    assert outcome.accounting.tool_calls == 1
    assert outcome.accounting.inference_calls == 2
    assert len(outcome.tool_results) == 1
    assert outcome.tool_results[0].status is ToolExecutionStatus.SUCCEEDED
    assert outcome.tool_results[0].tool_name == "search_corpus"
    # Same inference session across the continuation.
    assert outcome.session is not None
    assert outcome.session.inference_session_id
    # Usage aggregated across both turns.
    assert outcome.accounting.input_tokens > 0
    assert outcome.accounting.output_tokens > 0


def test_multi_tool_batch_end_to_end(tmp_path: Path) -> None:
    """inference #1 → 3 tool calls → 3 results → inference #2 → final."""
    _, _, _, retriever, _ = index_fixture(tmp_path)

    def handler(url: str, headers: dict, body: dict, timeout: float) -> TransportResponse:
        messages = body["messages"]
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if has_tool_result:
            return completion_response("done", finish_reason="stop")
        return completion_response(
            "",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": "search_corpus",
                        "arguments": '{"query": "query ' + str(i) + '"}',
                    },
                }
                for i in (1, 2, 3)
            ],
        )

    provider, _ = make_provider(handler)
    inference = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model="qwen3.7-max"
    )
    runtime = InMemoryResearchRuntime(retriever=retriever, inference=inference)

    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(model_requirement="qwen3.7-max"),
        context=("research question",),
    )
    outcome = runtime.run_tool_loop(request)

    assert outcome.status is LoopStatus.FINAL
    assert outcome.accounting.inference_calls == 2
    assert outcome.accounting.tool_calls == 3
    assert len(outcome.tool_results) == 3
    assert all(r.status is ToolExecutionStatus.SUCCEEDED for r in outcome.tool_results)
    assert [r.call_id for r in outcome.tool_results] == ["call_1", "call_2", "call_3"]
