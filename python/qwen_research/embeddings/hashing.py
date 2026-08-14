"""Deterministic, dependency-free local embedding provider.

This is the Phase 4 default embedding backend: a **feature-hashing** embedder
that maps text to a fixed-dimension L2-normalized vector by hashing word tokens
and character n-grams into signed buckets. It is:

- **fully deterministic** (same input → same vector),
- **offline** (no model download, no network),
- **CPU-only** (no CUDA/ML framework),
- **versioned** (the scheme is ``hash-ngram-v1``; a change to the scheme is a
  new version, so stale vectors are detected rather than silently mixed).

It is a lightweight orthographic/subword-similarity embedding, **not** a
pretrained transformer: it generalizes over shared morphology and subword
structure, but does not capture full synonym-level semantics. A transformer
provider (e.g. ``sentence-transformers``) is the documented future upgrade path
behind the same :class:`EmbeddingProvider` interface — it is deliberately out of
scope for Phase 4 (no large ML framework, no CUDA, offline-only).
"""

from __future__ import annotations

import hashlib
import math
import re

from qwen_research.embeddings.base import EmbeddingInfo, EmbeddingResult

_MODEL = "hash-ngram-v1"
_VERSION = "1"
_NGRAM_SIZES = (3, 4, 5)

#: A small stopword set so common function words do not dominate similarity.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on",
        "for", "with", "at", "by", "from", "is", "are", "was", "were", "be",
        "been", "as", "it", "its", "this", "that", "these", "those", "we",
        "you", "they", "he", "she", "which", "who", "whom", "not", "no",
        "do", "does", "did", "will", "would", "can", "could", "should",
        "about", "into", "over", "under", "between", "such", "than",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _hash_feature(feature: str) -> int:
    return int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")


def _features(text: str) -> set[str]:
    words = [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]
    features: set[str] = set(words)
    for word in words:
        for size in _NGRAM_SIZES:
            if len(word) >= size:
                features.update(word[i : i + size] for i in range(len(word) - size + 1))
    return features


class HashingEmbeddingProvider:
    """Feature-hashing embedding backend (``hash-ngram-v1``)."""

    def __init__(self, *, dimension: int = 256) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self._dimension = dimension

    def model_info(self) -> EmbeddingInfo:
        return EmbeddingInfo(
            model=_MODEL,
            version=_VERSION,
            dimension=self._dimension,
            distance_metric="cosine",
            normalization="l2",
        )

    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(self._embed(t) for t in texts),
            model=_MODEL,
            dimension=self._dimension,
        )

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._embed(text)

    def _embed(self, text: str) -> tuple[float, ...]:
        vec = [0.0] * self._dimension
        for feature in _features(text):
            h = _hash_feature(feature)
            sign = 1.0 if (h & 1) else -1.0
            index = (h >> 1) % self._dimension
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return tuple(vec)
        return tuple(v / norm for v in vec)


#: The default provider factory (kept separate so config can select providers).
def default_provider(*, dimension: int = 256) -> HashingEmbeddingProvider:
    return HashingEmbeddingProvider(dimension=dimension)
