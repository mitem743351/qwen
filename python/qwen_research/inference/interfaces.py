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
    ProviderLimits,
    ThinkingMode,
)


@runtime_checkable
class InferenceProvider(Protocol):
    """Provider-neutral model invocation surface.

    Capability discovery is **model-specific and contextual**: ``capabilities``
    accepts an optional model id plus an optional inference-mode intent so a
    provider can advertise the *effective* capabilities for that invocation
    (e.g. structured output may be unavailable while thinking is enabled).
    """

    def capabilities(
        self,
        model: str | None = None,
        *,
        thinking_mode: ThinkingMode | None = None,
    ) -> ProviderCapabilities:
        """Advertise what the (selected) model actually supports in this context."""
        ...

    def limits(self, model: str | None = None) -> ProviderLimits:
        """Return the quantitative limits of the (selected) model."""
        ...

    def model_info(self, model: str | None = None) -> ModelInfo:
        """Return identity and context-window information for a model."""
        ...

    def models(self) -> tuple[ModelInfo, ...]:
        """Return the catalog of models this provider exposes."""
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
    reasoning: bool = False,
    reasoning_budget: int | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    preserved_thinking: bool = False,
    tool_calling: bool = False,
    structured_output: bool = False,
    streaming: bool = False,
    parallel_generation: bool = False,
    context_caching: bool = False,
) -> InferencePolicy:
    """Construct an :class:`InferencePolicy` (convenience helper)."""
    return InferencePolicy(
        model_requirement=model_requirement,
        reasoning=reasoning,
        reasoning_budget=reasoning_budget,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        top_p=top_p,
        preserved_thinking=preserved_thinking,
        tool_calling=tool_calling,
        structured_output=structured_output,
        streaming=streaming,
        parallel_generation=parallel_generation,
        context_caching=context_caching,
    )
