"""Model registry (cached model metadata, refreshed on demand)."""

from __future__ import annotations

import time
from collections.abc import Callable

from qwen_research.domain.inference import ModelInfo


class ModelRegistry:
    """A cached view of available models for configured providers.

    ``refresh_fn`` returns the model list; it is called lazily and its result is
    cached for ``ttl_seconds`` so a network call is not made on every task.
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

    def list_models(self) -> tuple[ModelInfo, ...]:
        self._maybe_refresh()
        return self._cache or ()

    def get_model(self, model: str) -> ModelInfo | None:
        for info in self.list_models():
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
