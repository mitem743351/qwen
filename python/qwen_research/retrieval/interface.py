"""Retriever interface — independent of MCP and of any concrete index."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qwen_research.retrieval.models import (
    CorpusStats,
    DocumentView,
    IndexStatus,
    SearchOptions,
    SearchResult,
)


@runtime_checkable
class Retriever(Protocol):
    """A search interface over the corpus index."""

    def search(self, query: str, options: SearchOptions | None = None) -> SearchResult: ...

    def get_document(self, document_id: str) -> DocumentView | None: ...

    def stats(self) -> CorpusStats: ...

    def status(self) -> IndexStatus: ...
