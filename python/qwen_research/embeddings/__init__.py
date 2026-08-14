"""Embedding layer: provider abstraction and the default local backend."""

from qwen_research.embeddings.base import (
    EmbeddingInfo,
    EmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)
from qwen_research.embeddings.hashing import HashingEmbeddingProvider, default_provider
from qwen_research.embeddings.manager import EmbeddingManager, EmbeddingSyncReport

__all__ = [
    "EmbeddingInfo",
    "EmbeddingManager",
    "EmbeddingProvider",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingSyncReport",
    "HashingEmbeddingProvider",
    "default_provider",
]
