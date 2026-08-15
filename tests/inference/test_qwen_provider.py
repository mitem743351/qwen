"""Qwen provider adapter tests (fake transport — no live API key)."""

from __future__ import annotations

import pytest

from inference_helpers import (
    completion_response,
    json_response,
    make_provider,
    sse_response,
)
from qwen_research.common.ids import TaskId
from qwen_research.domain.errors import (
    ModelNotFoundError,
    ProviderAuthError,
    ProviderCredentialError,
    ProviderRateLimitError,
    ProviderServerError,
    StructuredOutputError,
)
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    Message,
    MessageRole,
    StreamEventType,
    ToolSpec,
)


def _request(**policy_kwargs: object) -> InferenceRequest:
    return InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(**policy_kwargs),  # type: ignore[arg-type]
        context=("What is the surface code?",),
    )


def test_request_mapping_and_normalization() -> None:
    provider, transport = make_provider(
        lambda *_: completion_response("The surface code is a QEC code.")
    )
    result = provider.generate(_request())
    assert result.status == "ok"
    assert result.content == "The surface code is a QEC code."
    assert result.finish_reason == "stop"
    assert result.usage == {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    # Request body mapping.
    url, headers, body, _ = transport.calls[0]
    assert url.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "qwen-max"
    assert body["messages"] == [{"role": "user", "content": "What is the surface code?"}]


def test_negotiated_policy_only_maps_supported_params() -> None:
    provider, transport = make_provider(
        lambda *_: completion_response("ok")
    )
    provider.generate(
        _request(max_output_tokens=100, temperature=0.5, top_p=0.9)
    )
    body = transport.calls[0][2]
    assert body["max_tokens"] == 100
    assert body["temperature"] == 0.5
    assert body["top_p"] == 0.9


def test_messages_mapped() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(),
        messages=(
            Message(role=MessageRole.SYSTEM, content="system prompt"),
            Message(role=MessageRole.USER, content="user prompt"),
        ),
    )
    provider.generate(request)
    body = transport.calls[0][2]
    assert body["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]


def test_finish_reasons_normalized() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response("truncated", finish_reason="length")
    )
    result = provider.generate(_request())
    assert result.finish_reason == "length"
    assert "output truncated (length)" in result.warnings


def test_tool_calls_normalized() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response(
            "",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "search", "arguments": '{"query": "x"}'},
                }
            ],
        )
    )
    result = provider.generate(_request(tool_calling=True))
    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls_structured) == 1
    call = result.tool_calls_structured[0]
    assert call.tool_name == "search"
    assert call.arguments == {"query": "x"}


def test_structured_output_parsed() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response('{"summary": "ok"}')
    )
    result = provider.generate(_request(structured_output=True))
    assert result.structured_output == {"summary": "ok"}


def test_structured_output_invalid_rejected() -> None:
    provider, _ = make_provider(lambda *_: completion_response("not json"))
    with pytest.raises(StructuredOutputError):
        provider.generate(_request(structured_output=True))


def test_streaming_events_normalized() -> None:
    provider, _ = make_provider(
        lambda *_: sse_response(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"finish_reason": "stop"}], "usage": {"total_tokens": 5}},
        )
    )
    events = list(provider.stream_events(_request()))
    text = "".join(e.text_delta for e in events if e.type is StreamEventType.TEXT_DELTA)
    assert text == "Hello"
    assert any(e.type is StreamEventType.COMPLETED for e in events)
    assert any(e.type is StreamEventType.USAGE for e in events)


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimitError),
        (500, ProviderServerError),
    ],
)
def test_error_statuses_normalized(status: int, exc: type) -> None:
    provider, _ = make_provider(
        lambda *_, status=status: json_response({"error": "x"}, status=status)
    )
    with pytest.raises(exc):
        provider.generate(_request())


def test_missing_credential_raises() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response("ok"), api_key=""
    )
    with pytest.raises(ProviderCredentialError):
        provider.generate(_request())


def test_model_not_found() -> None:
    provider, _ = make_provider(
        lambda *_: json_response(
            {"error": {"message": "model qwen-bogus not found"}}, status=404
        )
    )
    with pytest.raises(ModelNotFoundError):
        provider.generate(_request(model_requirement="qwen-bogus"))


def test_thinking_budget_emitted_on_supporting_model() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    provider.generate(
        _request(model_requirement="qwen3.7-max", reasoning=True, reasoning_budget=500)
    )
    body = transport.calls[0][2]
    assert body["enable_thinking"] is True
    assert body["thinking_budget"] == 500


def test_thinking_budget_omitted_on_non_supporting_model() -> None:
    # qwen-max is hybrid thinking but has no numeric thinking_budget.
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    provider.generate(
        _request(model_requirement="qwen-max", reasoning=True, reasoning_budget=500)
    )
    body = transport.calls[0][2]
    assert body["enable_thinking"] is True
    assert "thinking_budget" not in body


def test_preserve_thinking_emitted_on_supporting_model() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    provider.generate(
        _request(model_requirement="qwen3.7-max", preserved_thinking=True)
    )
    body = transport.calls[0][2]
    assert body["preserve_thinking"] is True


def test_preserve_thinking_omitted_on_non_supporting_model() -> None:
    # qwen-max does not support preserve_thinking.
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    provider.generate(
        _request(model_requirement="qwen-max", preserved_thinking=True)
    )
    body = transport.calls[0][2]
    assert "preserve_thinking" not in body


def test_full_tool_definitions_emitted() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    request = _request(tool_calling=True)
    request = InferenceRequest(
        task_reference=request.task_reference,
        inference_policy=request.inference_policy,
        tools=(
            ToolSpec(
                name="search_corpus",
                description="Search the local corpus.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
        ),
    )
    provider.generate(request)
    body = transport.calls[0][2]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_corpus",
                "description": "Search the local corpus.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]


def test_structured_output_validated_against_schema() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response('{"summary": "ok"}')
    )
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    result = provider.structured_output(_request(structured_output=True), schema)
    assert result.structured_output == {"summary": "ok"}


def test_structured_output_schema_violation_rejected() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response('{"other": 1}')
    )
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    with pytest.raises(StructuredOutputError):
        provider.structured_output(_request(structured_output=True), schema)


def test_structured_output_wrong_type_rejected() -> None:
    provider, _ = make_provider(
        lambda *_: completion_response('{"summary": 42}')
    )
    schema: dict[str, object] = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    with pytest.raises(StructuredOutputError):
        provider.structured_output(_request(structured_output=True), schema)
