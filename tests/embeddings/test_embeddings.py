"""Embedding provider tests: determinism, metadata, batches, versioning."""

from __future__ import annotations

import math

from qwen_research.embeddings.hashing import HashingEmbeddingProvider


def test_deterministic_dimension_and_metadata() -> None:
    provider = HashingEmbeddingProvider(dimension=256)
    info = provider.model_info()
    assert info.dimension == 256
    assert info.model == "hash-ngram-v1"
    assert info.version == "1"
    assert info.distance_metric == "cosine"
    assert provider.dimension() == 256


def test_embedding_is_deterministic() -> None:
    provider = HashingEmbeddingProvider(dimension=128)
    a = provider.embed_query("quantum error correction")
    b = provider.embed_query("quantum error correction")
    assert a == b


def test_embedding_is_normalized() -> None:
    provider = HashingEmbeddingProvider(dimension=128)
    vec = provider.embed_query("some text with several tokens")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-9 or norm == 0.0


def test_batch_behavior() -> None:
    provider = HashingEmbeddingProvider(dimension=64)
    texts = ["alpha beta", "gamma delta", "epsilon zeta"]
    result = provider.embed_documents(texts)
    assert result.model == "hash-ngram-v1"
    assert result.dimension == 64
    assert len(result.vectors) == 3


def test_empty_input() -> None:
    provider = HashingEmbeddingProvider(dimension=64)
    vec = provider.embed_query("")
    assert len(vec) == 64
    assert all(v == 0.0 for v in vec)
    assert provider.embed_documents([]).vectors == ()


def test_similar_texts_have_higher_similarity() -> None:
    provider = HashingEmbeddingProvider(dimension=256)

    def cos(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    q = provider.embed_query("quantum error correction thresholds")
    related = provider.embed_query("error correction in quantum computing")
    unrelated = provider.embed_query("ancient pottery kiln temperatures")
    assert cos(q, related) > cos(q, unrelated)


def test_invalid_dimension() -> None:
    import pytest

    with pytest.raises(ValueError):
        HashingEmbeddingProvider(dimension=0)
