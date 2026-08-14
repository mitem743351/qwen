"""Retrieval layer: lexical, semantic, hybrid, reranking, and models.

Concrete retrievers are imported lazily (they depend on the index/vector
interfaces, which import the leaf ``models`` module); importing them eagerly
would create a cycle.
"""

from qwen_research.retrieval.evidence import to_evidence
from qwen_research.retrieval.interface import Retriever
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexState,
    IndexStatus,
    RetrievalMode,
    RetrievalQuery,
    RetrievedChunk,
    SearchFilters,
    SearchOptions,
    SearchResult,
)
from qwen_research.retrieval.reranker import NoOpReranker, Reranker

__all__ = [
    "CorpusStats",
    "DocumentView",
    "IndexState",
    "IndexStatus",
    "NoOpReranker",
    "Reranker",
    "RetrievedChunk",
    "RetrievalMode",
    "RetrievalQuery",
    "Retriever",
    "SearchFilters",
    "SearchOptions",
    "SearchResult",
    "to_evidence",
]


def __getattr__(name: str) -> type:
    if name == "LexicalRetriever":
        from qwen_research.retrieval.lexical import LexicalRetriever

        return LexicalRetriever
    if name == "SemanticRetriever":
        from qwen_research.retrieval.semantic import SemanticRetriever

        return SemanticRetriever
    if name == "HybridRetriever":
        from qwen_research.retrieval.hybrid import HybridRetriever

        return HybridRetriever
    raise AttributeError(name)
