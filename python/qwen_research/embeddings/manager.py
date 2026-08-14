"""Incremental embedding manager.

Embeds only new/changed chunks, chunks missing an embedding, and chunks whose
embedding model/version changed. Vectors are keyed by the stable ``chunk_id``
and carry the model/version + a text hash so stale vectors are detectable, never
silently mixed with new-model vectors.
"""

from __future__ import annotations

import dataclasses
import hashlib

from qwen_research.embeddings.base import EmbeddingProvider
from qwen_research.indexing.interface import CorpusIndex
from qwen_research.vector.interface import VectorIndex, VectorRecord


@dataclasses.dataclass(frozen=True)
class EmbeddingSyncReport:
    """Counts produced by an embedding sync."""

    scanned: int
    embedded: int
    skipped: int
    deleted: int


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingManager:
    """Keeps the vector index in sync with the corpus index."""

    def __init__(
        self,
        corpus_index: CorpusIndex,
        vector_index: VectorIndex,
        provider: EmbeddingProvider,
        *,
        batch_size: int = 64,
    ) -> None:
        self._corpus = corpus_index
        self._vector = vector_index
        self._provider = provider
        self._batch_size = max(1, batch_size)

    def sync(self) -> EmbeddingSyncReport:
        """Embed new/changed chunks and drop stale vectors (idempotent)."""
        info = self._provider.model_info()
        chunks = self._corpus.list_chunks()
        current_ids = {c.chunk_id for c in chunks}
        existing_ids = set(self._vector.list_ids())

        to_embed = []
        for chunk in chunks:
            th = text_hash(chunk.text)
            record = self._vector.get(chunk.chunk_id)
            if (
                record is None
                or record.model != info.model
                or record.version != info.version
                or record.dimension != info.dimension
                or record.text_hash != th
            ):
                to_embed.append(chunk)

        embedded = 0
        for i in range(0, len(to_embed), self._batch_size):
            batch = to_embed[i : i + self._batch_size]
            result = self._provider.embed_documents([c.text for c in batch])
            records = [
                VectorRecord(
                    chunk_id=c.chunk_id,
                    model=info.model,
                    version=info.version,
                    dimension=info.dimension,
                    vector=v,
                    text_hash=text_hash(c.text),
                    distance_metric=info.distance_metric,
                    normalization=info.normalization,
                )
                for c, v in zip(batch, result.vectors, strict=True)
            ]
            self._vector.upsert(records)
            embedded += len(batch)

        # Delete vectors for chunks that no longer exist, or whose record is for
        # a different model/version (keeps the index from mixing models).
        stale: list[str] = []
        for chunk_id in existing_ids - current_ids:
            stale.append(chunk_id)
        for chunk_id in existing_ids & current_ids:
            record = self._vector.get(chunk_id)
            if record is not None and (
                record.model != info.model or record.version != info.version
            ):
                stale.append(chunk_id)
        deleted = self._vector.delete(stale) if stale else 0

        return EmbeddingSyncReport(
            scanned=len(chunks),
            embedded=embedded,
            skipped=len(chunks) - embedded,
            deleted=deleted,
        )
