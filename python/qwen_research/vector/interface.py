"""Vector index abstraction.

The retrieval and embedding layers depend on this interface; they never touch a
specific vector backend. Phase 4 uses a local SQLite-backed brute-force cosine
index (see :mod:`qwen_research.vector.sqlite`); sqlite-vec / FAISS are future
upgrades behind the same interface.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Protocol, runtime_checkable


@dataclasses.dataclass(frozen=True)
class VectorRecord:
    """An embedded chunk, tied to the model/version that produced it."""

    chunk_id: str
    model: str
    version: str
    dimension: int
    vector: tuple[float, ...]
    text_hash: str
    distance_metric: str = "cosine"
    normalization: str = "l2"


@dataclasses.dataclass(frozen=True)
class VectorHit:
    """A search hit: chunk id and similarity score."""

    chunk_id: str
    score: float


@runtime_checkable
class VectorIndex(Protocol):
    """Storage abstraction for chunk embeddings."""

    def initialize(self) -> None: ...

    def upsert(self, records: Iterable[VectorRecord]) -> None: ...

    def delete(self, chunk_ids: Iterable[str]) -> int: ...

    def search(
        self, vector: tuple[float, ...], *, model: str, version: str, limit: int
    ) -> list[VectorHit]:
        """Return the top-*limit* chunks by cosine similarity to *vector*."""
        ...

    def get(self, chunk_id: str) -> VectorRecord | None: ...

    def list_ids(self, *, model: str | None = None, version: str | None = None) -> list[str]: ...

    def stats(self) -> dict[str, int]: ...

    def rebuild(self) -> None: ...
