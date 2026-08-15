"""End-to-end MCP orchestration round-trip over stdio."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from orchestration_helpers import build_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


def _server_params(tmp_path: Path) -> StdioServerParameters:
    corpus = build_corpus(tmp_path)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_CORPUS_DB": str(tmp_path / "corpus.db"),
            "QWEN_RESEARCH_CORPUS_ROOT": str(corpus),
            "QWEN_RESEARCH_VECTOR_DB": str(tmp_path / "vector.db"),
            "QWEN_RESEARCH_MEMORY_DB": str(tmp_path / "memory.db"),
            "QWEN_RESEARCH_VERIFICATION_DB": str(tmp_path / "verification.db"),
            "QWEN_RESEARCH_ORCHESTRATION_DB": str(tmp_path / "orchestration.db"),
            "QWEN_RESEARCH_ENABLE_WRITE": "1",
        },
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_orchestration_roundtrip(tmp_path: Path) -> None:
    async def run() -> None:
        async with (
            stdio_client(_server_params(tmp_path)) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            for expected in (
                "plan_research",
                "start_research",
                "get_research_status",
                "get_research_summary",
                "pause_research",
                "resume_research",
                "cancel_research",
            ):
                assert expected in names

            # plan_research
            r = await session.call_tool(
                "plan_research",
                {"project_id": "p1", "description": "what is the surface code threshold"},
            )
            plan = json.loads(_text(r))
            plan_id = plan["plan_id"]
            assert plan["task_type"] in ("question_answering", "deep_research")
            assert plan["stages"]

            # start_research
            r = await session.call_tool("start_research", {"plan_id": plan_id})
            run = json.loads(_text(r))
            run_id = run["run_id"]
            assert run["status"] == "completed"

            # get_research_status
            r = await session.call_tool("get_research_status", {"run_id": run_id})
            assert json.loads(_text(r))["status"] == "completed"

            # get_research_summary
            r = await session.call_tool("get_research_summary", {"run_id": run_id})
            assert json.loads(_text(r))["status"] == "completed"

    asyncio.run(run())
