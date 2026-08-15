"""SynthesisRequest → InferenceRequest adapter.

The Phase 7 workflow produces a provider-neutral ``SynthesisRequest``; this
adapter turns it into an ``InferenceRequest`` (with prepared messages) for the
Inference Runtime. The workflow engine never learns Qwen-specific structures.
"""

from __future__ import annotations

from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    Message,
    MessageRole,
)
from qwen_research.orchestration.models import SynthesisRequest

_SYSTEM_PROMPT = (
    "You are a rigorous research synthesis assistant. Ground every claim in the "
    "provided evidence and clearly distinguish established findings, "
    "contradictions, and open questions. Do not fabricate evidence."
)


def synthesis_to_inference(
    synthesis: SynthesisRequest,
    *,
    policy: InferencePolicy | None = None,
    required_output: str | None = None,
) -> InferenceRequest:
    """Convert a synthesis boundary into a provider-neutral inference request.

    The Research Runtime has already assembled the context; the adapter only
    packages it into messages — it never fetches documents, memory, retrieval,
    claims, or computation independently.
    """
    user_content = _build_user_content(synthesis, required_output)
    messages = (
        Message(role=MessageRole.SYSTEM, content=_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    )
    return InferenceRequest(
        task_reference=synthesis.task_id,
        inference_policy=policy or InferencePolicy(),
        context=tuple(_context_fragments(synthesis)),
        messages=messages,
    )


def _build_user_content(synthesis: SynthesisRequest, required_output: str | None) -> str:
    parts: list[str] = [f"Objective: {synthesis.objective}"]
    summary = synthesis.research_summary
    if summary:
        parts.append("Research summary:")
        parts.append(_render_summary(summary))
    if required_output or synthesis.required_output:
        parts.append(f"Required output: {required_output or synthesis.required_output}")
    parts.append("Produce a structured synthesis draft grounded in the evidence above.")
    return "\n\n".join(parts)


def _render_summary(summary: dict[str, object]) -> str:
    lines = [f"- {key}: {value}" for key, value in sorted(summary.items())]
    return "\n".join(lines)


def _context_fragments(synthesis: SynthesisRequest) -> tuple[str, ...]:
    fragments: list[str] = [synthesis.objective]
    for key in sorted(synthesis.research_summary):
        value = synthesis.research_summary[key]
        if isinstance(value, (list, tuple)):
            for item in value:
                fragments.append(f"{key}: {item}")
        else:
            fragments.append(f"{key}: {value}")
    return tuple(fragments)
