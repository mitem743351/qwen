"""SynthesisRequest → InferenceRequest adapter tests."""

from __future__ import annotations

from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import InferencePolicy, MessageRole
from qwen_research.orchestration.models import SynthesisRequest
from qwen_research.research.synthesis import synthesis_to_inference


def _synthesis() -> SynthesisRequest:
    return SynthesisRequest(
        task_id=TaskId("task_1"),
        objective="What is the surface code threshold?",
        research_summary={
            "evidence_count": 3,
            "claim_count": 1,
            "contradiction_count": 0,
        },
        completion_state="ready_for_synthesis",
        required_output="structured synthesis draft",
        context=None,
    )


def test_synthesis_to_inference_builds_messages() -> None:
    request = synthesis_to_inference(_synthesis())
    assert request.task_reference == TaskId("task_1")
    roles = [m.role for m in request.messages]
    assert MessageRole.SYSTEM in roles
    assert MessageRole.USER in roles
    user = next(m for m in request.messages if m.role is MessageRole.USER)
    assert "surface code threshold" in user.content
    assert "evidence_count: 3" in user.content


def test_synthesis_respects_policy() -> None:
    policy = InferencePolicy(model_requirement="qwen-plus", max_output_tokens=200)
    request = synthesis_to_inference(_synthesis(), policy=policy)
    assert request.inference_policy.model_requirement == "qwen-plus"
    assert request.inference_policy.max_output_tokens == 200


def test_synthesis_context_fragments() -> None:
    request = synthesis_to_inference(_synthesis())
    assert request.context, "context fragments should be populated"
    assert any("evidence_count" in frag for frag in request.context)
