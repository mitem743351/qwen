"""End-to-end MCP computation round-trip over stdio."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


def _server_params(tmp_path: Path) -> StdioServerParameters:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "numbers.csv").write_text("group,value\nA,1.0\nA,2.0\nB,3.0\nB,5.0\nB,7.0\n")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_CORPUS_DB": str(tmp_path / "corpus.db"),
            "QWEN_RESEARCH_CORPUS_ROOT": str(corpus),
            "QWEN_RESEARCH_COMPUTATION_DB": str(tmp_path / "computation.db"),
            "QWEN_RESEARCH_WORKSPACE_ROOT": str(tmp_path / "workspace"),
            "QWEN_RESEARCH_ENABLE_WRITE": "1",
        },
    )


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_computation_roundtrip(tmp_path: Path) -> None:
    async def run() -> None:
        async with (
            stdio_client(_server_params(tmp_path)) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            for expected in (
                "describe_dataset",
                "run_query",
                "run_analysis",
                "get_computation_result",
                "run_python",
            ):
                assert expected in names

            # describe_dataset
            r = await session.call_tool(
                "describe_dataset",
                {"dataset": {"root_id": "corpus", "relative_path": "numbers.csv"}},
            )
            profile = json.loads(_text(r))
            assert profile["row_count"] == 5

            # run_analysis (aggregate)
            r = await session.call_tool(
                "run_analysis",
                {
                    "project_id": "p1",
                    "operation": "aggregate",
                    "datasets": [{"root_id": "corpus", "relative_path": "numbers.csv"}],
                    "parameters": {"column": "value", "function": "sum"},
                },
            )
            result = json.loads(_text(r))
            computation_id = result["computation_id"]
            assert result["status"] == "completed"
            assert result["value"] == 18.0

            # get_computation_result
            r = await session.call_tool(
                "get_computation_result", {"project_id": "p1", "computation_id": computation_id}
            )
            assert json.loads(_text(r))["computation_id"] == computation_id

    asyncio.run(run())


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_run_python_denied_without_execute(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_COMPUTATION_DB": str(tmp_path / "computation.db"),
        },
    )

    async def run() -> None:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            with pytest.raises(Exception) as exc:
                await session.call_tool("run_python", {"project_id": "p", "source": "RESULT = 1"})
            assert "permission denied" in str(exc.value)

    asyncio.run(run())
