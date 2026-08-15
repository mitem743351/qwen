"""The application-level Inference Runtime.

Owns provider selection, capability negotiation, request validation, timeout and
retry handling, usage accounting, and invocation-metadata persistence. It does
**not** own research planning, retrieval, memory, verification, workflow
orchestration, or claim management.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import TYPE_CHECKING

from qwen_research.common.timestamps import utc_now
from qwen_research.domain.errors import (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
)
from qwen_research.domain.inference import (
    InferencePolicy,
    InferenceRequest,
    InferenceResult,
    InferenceStreamEvent,
    ModelInfo,
    ProviderCapabilities,
    StructuredOutputSpec,
    negotiate,
)
from qwen_research.inference.config import RetryConfig
from qwen_research.inference.interfaces import InferenceProvider
from qwen_research.inference.models import InvocationMetadata, ProviderHealth
from qwen_research.inference.router import InferenceRouter

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from qwen_research.inference.store import InvocationStore

#: Errors that are *transient* and may be retried (never auth/invalid/content).
_RETRYABLE_EXCEPTIONS = (
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
)


class InferenceRuntime:
    """Provider-neutral inference execution over registered providers."""

    def __init__(
        self,
        providers: dict[str, InferenceProvider],
        *,
        default_provider: str,
        default_model: str = "",
        retry: RetryConfig | None = None,
        store: InvocationStore | None = None,
    ) -> None:
        self._router = InferenceRouter(
            providers, default_provider=default_provider, default_model=default_model
        )
        self._providers = providers
        self._default_provider = default_provider
        self._retry = retry or RetryConfig()
        self._store = store

    # -- capability / model discovery -------------------------------------

    def capabilities(self, provider_id: str | None = None) -> ProviderCapabilities:
        route = self._router.select(InferencePolicy(), provider_id=provider_id)
        return route.provider.capabilities()

    def models(self, provider_id: str | None = None) -> tuple[ModelInfo, ...]:
        return tuple(self._router.models(provider_id))

    def health(self, provider_id: str | None = None) -> ProviderHealth:
        provider_id = provider_id or self._default_provider
        provider = self._providers.get(provider_id)
        if provider is None:
            return ProviderHealth(available=False, last_error=f"unknown provider {provider_id!r}")
        health_method = getattr(provider, "health", None)
        if health_method is not None:
            result = health_method()
            return result if isinstance(result, ProviderHealth) else ProviderHealth(available=True)
        return ProviderHealth(available=True, capabilities=provider.capabilities())

    # -- invocation --------------------------------------------------------

    def generate(
        self,
        request: InferenceRequest,
        *,
        provider_id: str | None = None,
        profile: str = "",
    ) -> InferenceResult:
        """One-shot generation with negotiation, retry, and usage accounting."""
        route = self._router.select(request.inference_policy, provider_id=provider_id)
        negotiation = negotiate(request.inference_policy, route.provider.capabilities())
        # Re-seat the policy to only what the provider actually receives.
        request = _with_policy(request, negotiation.provider_policy)
        metadata = InvocationMetadata.create(
            task_id=request.task_reference,
            session_id=None,
            provider=route.provider_id,
            model=route.model,
            profile=profile,
        )
        started = time.monotonic()
        try:
            result = self._with_retry(lambda: route.provider.generate(request))
        except Exception as exc:  # noqa: BLE001 — record failure metadata
            self._record_failure(metadata, exc)
            raise
        self._record_success(metadata, result, time.monotonic() - started)
        return result

    def stream(
        self,
        request: InferenceRequest,
        *,
        provider_id: str | None = None,
    ) -> Iterator[InferenceStreamEvent]:
        """Normalized streaming (events, not raw provider SSE)."""
        route = self._router.select(request.inference_policy, provider_id=provider_id)
        negotiation = negotiate(request.inference_policy, route.provider.capabilities())
        request = _with_policy(request, negotiation.provider_policy)
        stream_events = getattr(route.provider, "stream_events", None)
        if stream_events is not None:
            yield from stream_events(request)
            return
        # Fallback: the protocol's stream() returns a single accumulated result.
        for result in route.provider.stream(request):
            if result.content:
                from qwen_research.domain.inference import StreamEventType

                yield InferenceStreamEvent(
                    type=StreamEventType.TEXT_DELTA, text_delta=result.content
                )
            yield InferenceStreamEvent(
                type=StreamEventType.COMPLETED,
                finish_reason=result.finish_reason,
                usage=result.usage,
                error=result.errors[0] if result.errors else None,
            )

    def structured(
        self,
        request: InferenceRequest,
        spec: StructuredOutputSpec,
        *,
        provider_id: str | None = None,
        profile: str = "",
    ) -> InferenceResult:
        route = self._router.select(request.inference_policy, provider_id=provider_id)
        capabilities = route.provider.capabilities()
        if not capabilities.supports_structured_output:
            # Structured output is workflow-emulatable; the Research Runtime may
            # post-validate, but this runtime will not fabricate native support.
            from qwen_research.domain.errors import StructuredOutputError

            raise StructuredOutputError(
                "structured output not natively supported by provider; "
                "use workflow emulation (post-validation) instead"
            )
        policy = request.inference_policy
        request = _with_policy(
            request, InferencePolicy(**{**policy.__dict__, "structured_output": True})
        )
        metadata = InvocationMetadata.create(
            task_id=request.task_reference,
            session_id=None,
            provider=route.provider_id,
            model=route.model,
            profile=profile,
        )
        started = time.monotonic()
        try:
            result = self._with_retry(
                lambda: route.provider.structured_output(request, spec.schema)
            )
        except Exception as exc:  # noqa: BLE001
            self._record_failure(metadata, exc)
            raise
        self._record_success(metadata, result, time.monotonic() - started)
        return result

    # -- retry -------------------------------------------------------------

    def _with_retry(self, fn: Callable[[], InferenceResult]) -> InferenceResult:
        attempt = 0
        while True:
            try:
                return fn()
            except _RETRYABLE_EXCEPTIONS:
                attempt += 1
                if attempt >= self._retry.max_attempts:
                    raise
                backoff = min(
                    self._retry.base_backoff_seconds * (2 ** (attempt - 1)),
                    self._retry.max_backoff_seconds,
                )
                time.sleep(backoff)

    # -- persistence -------------------------------------------------------

    def _record_success(
        self, metadata: InvocationMetadata, result: InferenceResult, latency_ms: float
    ) -> None:
        if self._store is None:
            return
        completed = _now()
        self._store.save(
            dataclasses.replace(
                metadata,
                status=result.status,
                finish_reason=result.finish_reason,
                usage=dict(result.usage or {}),
                completed_at=completed,
                latency_ms=round(latency_ms * 1000, 3),
                error=result.errors[0] if result.errors else None,
            )
        )

    def _record_failure(self, metadata: InvocationMetadata, exc: Exception) -> None:
        if self._store is None:
            return
        self._store.save(
            dataclasses.replace(
                metadata,
                status="error",
                completed_at=_now(),
                error=f"{type(exc).__name__}: {exc}",
            )
        )


def _with_policy(request: InferenceRequest, policy: InferencePolicy) -> InferenceRequest:
    return dataclasses.replace(request, inference_policy=policy)


def _now() -> datetime:
    return utc_now()
