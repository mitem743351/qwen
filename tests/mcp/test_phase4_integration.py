"""End-to-end MCP integration: hybrid search + persistent memory over stdio.

Spawns the real MCP server with a corpus + vector index + memory store (via the
documented environment variables), then exercises hybrid ``search_corpus`` and
the memory tools through the official MCP client — the same path Qwen Studio
uses. No Qwen API or network.
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

from phase4_helpers import copy_semantic_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_hybrid_and_memory_roundtrip(tmp_path: Path) -> None:
    corpus = copy_semantic_corpus(tmp_path)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_CORPUS_DB": str(tmp_path / "corpus.db"),
            "QWEN_RESEARCH_CORPUS_ROOT": str(corpus),
            "QWEN_RESEARCH_VECTOR_DB": str(tmp_path / "vectors.db"),
            "QWEN_RESEARCH_MEMORY_DB": str(tmp_path / "memory.db"),
            "QWEN_RESEARCH_ENABLE_WRITE": "1",
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
            for expected in (
                "search_corpus",
                "get_project_memory",
                "get_research_memory",
                "get_open_questions",
                "save_research_memory",
            ):
                assert expected in names

            # Hybrid search (default mode) over the semantic corpus.
            r = await session.call_tool(
                "search_corpus",
                {
                    "query": "methods for reducing quantum error rates",
                    "mode": "hybrid",
                    "limit": 3,
                },
            )
            result = json.loads(_text(r))
            assert result["mode"] == "hybrid"
            assert len(result["results"]) >= 1
            assert result["results"][0]["document_id"]

            # save_research_memory (WRITE permission enabled).
            r = await session.call_tool(
                "save_research_memory",
                {
                    "project_id": "p1",
                    "content": "surface code threshold ~1%",
                    "source_refs": ["src_1"],
                },
            )
            memory = json.loads(_text(r))
            assert memory["project_id"] == "p1"
            assert memory["source_refs"] == ["src_1"]

            # get_research_memory returns it (project isolation).
            r = await session.call_tool("get_research_memory", {"project_id": "p1"})
            hits = json.loads(_text(r))
            assert len(hits["memories"]) == 1
            assert hits["memories"][0]["content"] == "surface code threshold ~1%"

            # Another project sees nothing.
            r = await session.call_tool("get_research_memory", {"project_id": "p2"})
            assert json.loads(_text(r))["memories"] == []

            # get_open_questions is empty but well-formed.
            r = await session.call_tool("get_open_questions", {"project_id": "p1"})
            assert json.loads(_text(r))["questions"] == []

    asyncio.run(run())


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_save_memory_denied_without_write(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_MEMORY_DB": str(tmp_path / "memory.db"),
            # write not enabled → save_research_memory must be denied.
        },
    )

    async def run() -> None:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            with pytest.raises(MCPError) as exc:
                await session.call_tool(
                    "save_research_memory", {"project_id": "p", "content": "x"}
                )
            assert "permission denied" in exc.value.message

    asyncio.run(run())
