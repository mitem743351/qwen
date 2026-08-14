"""Retrieval layer: ranking, evidence selection, and models.

``LexicalRetriever`` lives in :mod:`qwen_research.retrieval.lexical` and is
imported lazily (it depends on the index interface, which in turn imports the
leaf ``models`` module); importing it here eagerly would create a cycle.
"""

from qwen_research.retrieval.evidence import to_evidence
from qwen_research.retrieval.interface import Retriever
from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexState,
    IndexStatus,
    RetrievedChunk,
    SearchFilters,
    SearchOptions,
    SearchResult,
)

__all__ = [
    "CorpusStats",
    "DocumentView",
    "IndexState",
    "IndexStatus",
    "RetrievedChunk",
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
    raise AttributeError(name)
