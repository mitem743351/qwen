"""Simple explicit provider router (no autonomous model switching)."""

from __future__ import annotations

import dataclasses

from qwen_research.domain.errors import ProviderConfigurationError
from qwen_research.domain.inference import InferencePolicy, ModelInfo
from qwen_research.inference.interfaces import InferenceProvider


@dataclasses.dataclass(frozen=True)
class Route:
    """A resolved (provider, model) selection."""

    provider_id: str
    provider: InferenceProvider
    model: str


class InferenceRouter:
    """Explicit provider + default-model routing.

    No load balancing and no autonomous model switching: an explicit provider
    plus an explicit default model. An unknown model raises
    :class:`ModelNotFoundError` rather than silently substituting another.
    """

    def __init__(
        self,
        providers: dict[str, InferenceProvider],
        *,
        default_provider: str,
        default_model: str,
    ) -> None:
        self._providers = providers
        self._default_provider = default_provider
        self._default_model = default_model

    def select(self, policy: InferencePolicy, *, provider_id: str | None = None) -> Route:
        provider_id = provider_id or self._default_provider
        if not provider_id or provider_id not in self._providers:
            raise ProviderConfigurationError(f"unknown provider {provider_id!r}")
        provider = self._providers[provider_id]
        model = policy.model_requirement or self._default_model
        if not model:
            raise ProviderConfigurationError(
                f"no model selected for provider {provider_id!r} "
                "(set a model_requirement or a default_model)"
            )
        return Route(provider_id=provider_id, provider=provider, model=model)

    def models(self, provider_id: str | None = None) -> tuple[ModelInfo, ...]:
        provider_id = provider_id or self._default_provider
        provider = self._providers.get(provider_id)
        if provider is None:
            return ()
        return (provider.model_info(),)
