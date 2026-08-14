"""End-to-end MCP retrieval integration test over stdio.

Spawns the real MCP server with a local corpus (via the documented environment
variables), then exercises ``search_corpus`` and ``get_source`` through the
official MCP client — the same path Qwen Studio uses. No Qwen API or network.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent

from corpus_helpers import copy_fixture_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_retrieval_roundtrip(tmp_path: Path) -> None:
    corpus = copy_fixture_corpus(tmp_path)
    db = tmp_path / "corpus.db"

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_CORPUS_DB": str(db),
            "QWEN_RESEARCH_CORPUS_ROOT": str(corpus),
        },
    )

    async def run() -> None:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            assert "search_corpus" in names
            assert "get_source" in names

            # search_corpus
            r = await session.call_tool(
                "search_corpus", {"query": "surface code", "limit": 3}
            )
            result = json.loads(_text(r))
            assert result["query"] == "surface code"
            assert len(result["results"]) >= 1
            first = result["results"][0]
            assert first["chunk_id"]
            assert first["document_id"]
            assert first["path"]
            assert first["excerpt"]
            assert isinstance(first["score"], (int, float))

            # get_source
            doc_id = first["document_id"]
            r = await session.call_tool("get_source", {"document_id": doc_id})
            doc = json.loads(_text(r))
            assert doc["document_id"] == doc_id
            assert doc["media_type"]
            assert doc["title"]

            # Safe error: unknown document id → clean "not found" error.
            with pytest.raises(MCPError) as exc:
                await session.call_tool("get_source", {"document_id": "doc_missing"})
            assert exc.value.code == -32602
            assert "not found" in exc.value.message

            # A document id is an opaque identifier, never a filesystem path;
            # a traversal-looking string cannot escape the corpus.
            with pytest.raises(MCPError):
                await session.call_tool("get_source", {"document_id": "../../etc/passwd"})

    asyncio.run(run())
