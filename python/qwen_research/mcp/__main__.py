"""CLI entry point: run the MCP server over stdio.

Usage: ``python -m qwen_research.mcp``

By default the server exposes the Research Runtime with **no** corpus. To serve
a local corpus, set the environment variables ``QWEN_RESEARCH_CORPUS_DB`` (path
to the SQLite index database) and ``QWEN_RESEARCH_CORPUS_ROOT`` (an allowlisted
corpus directory). On startup the corpus is incrementally indexed, then the
``search_corpus`` and ``get_source`` tools serve ranked evidence.

Local-only: no network socket is opened.
"""

from __future__ import annotations

import os

from qwen_research.mcp.server import run_stdio_server
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.research.runtime import InMemoryResearchRuntime


def build_runtime() -> ResearchRuntime:
    """Build the Research Runtime, optionally wired to a local corpus."""
    db = os.environ.get("QWEN_RESEARCH_CORPUS_DB")
    root = os.environ.get("QWEN_RESEARCH_CORPUS_ROOT")
    if db and root:
        from qwen_research.corpus.config import CorpusConfig, CorpusRoot
        from qwen_research.indexing.manager import IndexManager
        from qwen_research.indexing.sqlite import SqliteCorpusIndex
        from qwen_research.retrieval.lexical import LexicalRetriever

        config = CorpusConfig(
            roots=(
                CorpusRoot(root_id="corpus", path=root, read_only=True, recursive=True),
            )
        )
        index = SqliteCorpusIndex(db)
        IndexManager(config, index).index_all()
        return InMemoryResearchRuntime(retriever=LexicalRetriever(index))
    return InMemoryResearchRuntime()


def main() -> None:
    run_stdio_server(build_runtime())


if __name__ == "__main__":
    main()
