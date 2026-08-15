"""Serialization determinism, version-awareness, and round-trips."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import SCHEMA_VERSION, dumps, loads
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    ProviderCapabilities,
    ToolSpec,
)
from qwen_research.domain.reasoning import DEEP
from qwen_research.domain.research import Hypothesis, ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.source import Source, SourceType
from qwen_research.domain.task import TaskStatus


def test_dumps_is_deterministic() -> None:
    session = Session.create()
    assert dumps(session) == dumps(session)


def test_roundtrip_preserves_equality() -> None:
    source = Source.create("https://x.example/a", "A", SourceType.WEB, author="alice")
    assert loads(dumps(source)) == source


def test_roundtrip_nested_structures() -> None:
    state = ResearchState(
        task_id=TaskId("task_1"),
        current_stage=TaskStatus.PLANNED,
        hypotheses=(Hypothesis("h1"), Hypothesis("h2")),
    )
    assert loads(dumps(state)) == state


def test_roundtrip_enums_and_optional_datetimes() -> None:
    source = Source.create(
        "https://x.example/a", "A", SourceType.PAPER, publication_date=None
    )
    restored = loads(dumps(source))
    assert restored.source_type is SourceType.PAPER
    assert restored.publication_date is None


def test_roundtrip_reasoning_objects() -> None:
    assert loads(dumps(DEEP)) == DEEP
    assert loads(dumps(DEEP.budget())) == DEEP.budget()


def test_roundtrip_inference_objects() -> None:
    capabilities = ProviderCapabilities(
        supports_reasoning=True,
        supports_tool_calling=True,
        supports_structured_output=True,
    )
    policy = InferencePolicy(
        model_requirement="reasoning",
        reasoning=True,
        reasoning_budget=100,
        max_output_tokens=500,
        temperature=0.7,
        top_p=0.9,
        tool_calling=True,
        structured_output=True,
    )
    request = InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=policy,
        context=("evidence-1", "evidence-2"),
        tools=(ToolSpec(name="retrieve", description="search", parameters={"type": "object"}),),
    )
    result = InferenceResult(
        status="ok",
        model="qwen-xyz",
        content="answer",
        structured_output={"summary": "x"},
        usage={"input": 10, "output": 20},
        warnings=("degraded-streaming",),
    )
    for obj in (capabilities, policy, request, result):
        assert loads(dumps(obj)) == obj


def test_roundtrip_runtime_contracts() -> None:
    from qwen_research.research.interfaces import MCPRequest, MCPResult

    request = MCPRequest(
        tool="get_research_state",
        arguments={"task_id": "task_1"},
        session_reference="session_1",
        permission_context=("read",),
    )
    result = MCPResult(
        status="ok",
        result={"status": "planned"},
        citations=("source_1",),
        provenance={"workflow": "placeholder"},
        errors=(),
    )
    assert loads(dumps(request)) == request
    assert loads(dumps(result)) == result


def test_serialization_has_no_chain_of_thought() -> None:
    result = InferenceResult(status="ok", model="m", content="answer")
    serialized = dumps(result)
    assert "chain_of_thought" not in serialized
    assert "thinking" not in serialized.lower()


def test_schema_version_present() -> None:
    payload = dumps(Session.create())
    assert '"schema_version": 1' in payload


def test_unknown_type_rejected() -> None:
    import json

    payload = json.dumps({"schema_version": SCHEMA_VERSION, "type": "no.such.Type", "data": {}})
    with pytest.raises(ValueError):
        loads(payload)


def test_unsupported_version_rejected() -> None:
    import json

    payload = json.dumps({"schema_version": 999, "type": "x", "data": {}})
    with pytest.raises(ValueError):
        loads(payload)
