"""CLI entry point: run the MCP server over stdio.

Usage: ``python -m qwen_research.mcp``

Optional environment configuration:

- ``QWEN_RESEARCH_CORPUS_DB`` + ``QWEN_RESEARCH_CORPUS_ROOT`` — index a local
  corpus (SQLite FTS5) and expose ``search_corpus``/``get_source``.
- ``QWEN_RESEARCH_VECTOR_DB`` — enable semantic retrieval (embeddings stored in
  a local vector index). Combined with the corpus DB, ``search_corpus`` becomes
  hybrid by default.
- ``QWEN_RESEARCH_MEMORY_DB`` — enable persistent structured memory and the
  ``get_*_memory`` / ``save_research_memory`` tools.

Local-only: no network socket is opened.
"""

from __future__ import annotations

import os

from qwen_research.mcp.server import run_stdio_server
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.research.runtime import InMemoryResearchRuntime


def build_runtime() -> ResearchRuntime:
    """Build the Research Runtime, optionally wired to corpus/vectors/memory."""
    from qwen_research.retrieval.interface import Retriever

    retriever: Retriever | None = None
    memory = None

    corpus_db = os.environ.get("QWEN_RESEARCH_CORPUS_DB")
    corpus_root = os.environ.get("QWEN_RESEARCH_CORPUS_ROOT")
    vector_db = os.environ.get("QWEN_RESEARCH_VECTOR_DB")
    memory_db = os.environ.get("QWEN_RESEARCH_MEMORY_DB")

    if corpus_db and corpus_root:
        from qwen_research.corpus.config import CorpusConfig, CorpusRoot
        from qwen_research.indexing.manager import IndexManager
        from qwen_research.indexing.sqlite import SqliteCorpusIndex
        from qwen_research.retrieval.lexical import LexicalRetriever

        config = CorpusConfig(
            roots=(CorpusRoot(root_id="corpus", path=corpus_root, read_only=True, recursive=True),)
        )
        index = SqliteCorpusIndex(corpus_db)
        IndexManager(config, index).index_all()
        lexical = LexicalRetriever(index)

        if vector_db:
            from qwen_research.embeddings.hashing import HashingEmbeddingProvider
            from qwen_research.embeddings.manager import EmbeddingManager
            from qwen_research.retrieval.hybrid import HybridRetriever
            from qwen_research.retrieval.semantic import SemanticRetriever
            from qwen_research.vector.sqlite import SqliteVectorIndex

            provider = HashingEmbeddingProvider()
            vector_index = SqliteVectorIndex(vector_db)
            vector_index.initialize()
            EmbeddingManager(index, vector_index, provider).sync()
            hybrid = HybridRetriever(
                lexical,
                SemanticRetriever(index, vector_index, provider),
            )
            retriever = hybrid
        else:
            retriever = lexical

    if memory_db:
        from qwen_research.memory.service import MemoryService
        from qwen_research.memory.sqlite import SqliteMemoryStore

        store = SqliteMemoryStore(memory_db)
        store.initialize()
        memory = MemoryService(store)

    return InMemoryResearchRuntime(retriever=retriever, memory=memory)


def main() -> None:
    config = None
    if os.environ.get("QWEN_RESEARCH_ENABLE_WRITE") == "1":
        from qwen_research.mcp.config import MCPServerConfig

        config = MCPServerConfig(
            permissions={
                "read": True,
                "analyze": True,
                "write": True,
                "execute": False,
                "destructive": False,
            }
        )
    run_stdio_server(build_runtime(), config)


if __name__ == "__main__":
    main()
