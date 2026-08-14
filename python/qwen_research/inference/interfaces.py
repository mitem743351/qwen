"""The provider-independent ``InferenceProvider`` contract.

The Inference Runtime owns provider/model selection, capability discovery,
policy translation, invocation, and response normalization. This protocol is
the boundary the Research Runtime depends on; it must never leak provider
specifics upward.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    ModelInfo,
    ProviderCapabilities,
)


@runtime_checkable
class InferenceProvider(Protocol):
    """Provider-neutral model invocation surface."""

    def capabilities(self) -> ProviderCapabilities:
        """Advertise what this provider actually supports (facts, not assumptions)."""
        ...

    def model_info(self) -> ModelInfo:
        """Return identity and context-window information."""
        ...

    def generate(self, request: InferenceRequest) -> InferenceResult:
        """One-shot completion."""
        ...

    def stream(self, request: InferenceRequest) -> Iterator[InferenceResult]:
        """Streaming completion."""
        ...

    def structured_output(
        self, request: InferenceRequest, schema: dict[str, object]
    ) -> InferenceResult:
        """Constrained/typed output."""
        ...


def build_policy(
    *,
    model_requirement: str | None = None,
    sampling: str | None = None,
    max_output_tokens: int | None = None,
    require_structured_output: bool = False,
    allow_tool_calling: bool = False,
    prefer_streaming: bool = False,
    budget: int | None = None,
) -> InferencePolicy:
    """Construct an :class:`InferencePolicy` (convenience helper)."""
    return InferencePolicy(
        model_requirement=model_requirement,
        sampling=sampling,
        max_output_tokens=max_output_tokens,
        require_structured_output=require_structured_output,
        allow_tool_calling=allow_tool_calling,
        prefer_streaming=prefer_streaming,
        budget=budget,
    )
