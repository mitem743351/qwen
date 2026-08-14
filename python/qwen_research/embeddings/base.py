"""Embedding provider abstraction.

Embeddings are a local, deterministic concern in Phase 4. The provider
interface keeps retrieval independent of any particular model or backend, and
records enough metadata (model identity, version, dimension, distance metric,
normalization) to detect stale embeddings.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class EmbeddingInfo:
    """Identity and shape metadata for an embedding model."""

    model: str
    version: str
    dimension: int
    distance_metric: str = "cosine"
    normalization: str = "l2"


@dataclasses.dataclass(frozen=True)
class EmbeddingRequest:
    """A batch embedding request."""

    texts: tuple[str, ...]
    model: str
    batch_size: int = 64


@dataclasses.dataclass(frozen=True)
class EmbeddingResult:
    """A batch of embedding vectors."""

    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimension: int


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A local, deterministic embedding backend."""

    def model_info(self) -> EmbeddingInfo: ...

    def dimension(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> EmbeddingResult: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...
