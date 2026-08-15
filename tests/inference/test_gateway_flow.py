"""GATEWAY_INFERENCE end-to-end flow (fake transport; single invocation)."""

from __future__ import annotations

from inference_helpers import completion_response, make_provider
from qwen_research.common.ids import TaskId
from qwen_research.domain.inference import InferencePolicy
from qwen_research.inference.runtime import InferenceRuntime
from qwen_research.orchestration.models import SynthesisRequest
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.research.synthesis import synthesis_to_inference


def test_single_inference_flow_through_runtime() -> None:
    provider, _ = make_provider(lambda *_: completion_response("The threshold is ~1%."))
    runtime = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model="qwen-max"
    )
    research = InMemoryResearchRuntime(inference=runtime)

    synthesis = SynthesisRequest(
        task_id=TaskId("task_1"),
        objective="What is the surface code threshold?",
        research_summary={"evidence_count": 3, "claim_count": 1},
        completion_state="ready_for_synthesis",
        required_output="structured synthesis draft",
    )
    result = research.synthesize(synthesis, policy=InferencePolicy(model_requirement="qwen-max"))
    assert result.ok
    assert result.content == "The threshold is ~1%."
    assert result.provider == "qwen"
    assert result.usage is not None


def test_synthesis_adapter_feeds_runtime() -> None:
    provider, transport = make_provider(lambda *_: completion_response("ok"))
    runtime = InferenceRuntime(
        {"qwen": provider}, default_provider="qwen", default_model="qwen-max"
    )
    synthesis = SynthesisRequest(
        task_id=TaskId("task_1"),
        objective="objective",
        research_summary={},
        completion_state="ready_for_synthesis",
        required_output="draft",
    )
    request = synthesis_to_inference(synthesis)
    runtime.generate(request)
    # The provider received a system + user message (adapter produced messages).
    body = transport.calls[0][2]
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user"]
