"""Model registry (cached model metadata, refreshed on demand)."""

from __future__ import annotations

import time
from collections.abc import Callable

from qwen_research.domain.inference import (
    AvailabilityPlan,
    ModelAvailability,
    ModelInfo,
)


class ModelRegistry:
    """A cached view of available models for configured providers.

    ``refresh_fn`` returns the model list; it is called lazily and its result is
    cached for ``ttl_seconds`` so a network call is not made on every task.
    Resolution is lightweight and deterministic: ``get_model`` filters by model
    id plus optional plan / region / availability, matching only the metadata a
    provider exposes in :class:`ModelInfo`.
    """

    def __init__(
        self,
        refresh_fn: Callable[[], tuple[ModelInfo, ...]],
        *,
        ttl_seconds: float = 300.0,
    ) -> None:
        self._refresh_fn = refresh_fn
        self._ttl = ttl_seconds
        self._cache: tuple[ModelInfo, ...] | None = None
        self._cached_at: float = 0.0

    def list_models(
        self,
        *,
        plan: AvailabilityPlan | None = None,
        region: str | None = None,
        availability: ModelAvailability | None = None,
    ) -> tuple[ModelInfo, ...]:
        self._maybe_refresh()
        result = self._cache or ()
        if plan is not None:
            result = tuple(
                i for i in result if not i.plans or plan in i.plans
            )
        if region is not None:
            result = tuple(
                i for i in result if not i.regions or region in i.regions
            )
        if availability is not None:
            result = tuple(i for i in result if i.availability is availability)
        return result

    def get_model(
        self,
        model: str,
        *,
        plan: AvailabilityPlan | None = None,
        region: str | None = None,
    ) -> ModelInfo | None:
        for info in self.list_models(plan=plan, region=region):
            if info.model == model:
                return info
        return None

    def refresh(self) -> tuple[ModelInfo, ...]:
        self._cache = self._refresh_fn()
        self._cached_at = time.monotonic()
        return self._cache

    def _maybe_refresh(self) -> None:
        if self._cache is None or (time.monotonic() - self._cached_at) > self._ttl:
            self.refresh()
