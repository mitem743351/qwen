"""End-to-end MCP verification round-trip over stdio.

Spawns the real MCP server with a corpus + verification store, then exercises
the Phase 5 tools through the official MCP client. No Qwen API or network.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from phase4_helpers import copy_semantic_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    item = result.content[0]
    assert isinstance(item, TextContent)
    return item.text


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_mcp_verification_roundtrip(tmp_path: Path) -> None:
    corpus = copy_semantic_corpus(tmp_path)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_CORPUS_DB": str(tmp_path / "corpus.db"),
            "QWEN_RESEARCH_CORPUS_ROOT": str(corpus),
            "QWEN_RESEARCH_VERIFICATION_DB": str(tmp_path / "verification.db"),
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
                "create_claim",
                "link_claim_evidence",
                "assess_evidence",
                "verify_claim",
                "get_verification_report",
                "get_contradictions",
            ):
                assert expected in names

            # create_claim
            r = await session.call_tool(
                "create_claim",
                {"project_id": "p1", "text": "surface code threshold", "claim_type": "factual"},
            )
            claim = json.loads(_text(r))
            claim_id = claim["claim_id"]
            assert claim["status"] == "unreviewed"

            # search to find evidence
            r = await session.call_tool(
                "search_corpus", {"query": "surface code threshold", "limit": 1}
            )
            evidence_id = json.loads(_text(r))["results"][0]["chunk_id"]

            # link_claim_evidence
            r = await session.call_tool(
                "link_claim_evidence",
                {
                    "project_id": "p1",
                    "claim_id": claim_id,
                    "evidence_id": evidence_id,
                    "relationship": "supports",
                },
            )
            link = json.loads(_text(r))
            assert link["relationship"] == "supports"

            # assess_evidence
            r = await session.call_tool(
                "assess_evidence",
                {"project_id": "p1", "claim_id": claim_id, "evidence_id": evidence_id},
            )
            assessment = json.loads(_text(r))
            assert assessment["support_type"] == "direct_support"

            # verify_claim
            r = await session.call_tool("verify_claim", {"project_id": "p1", "claim_id": claim_id})
            report = json.loads(_text(r))
            report_id = report["report_id"]
            assert report["status"] in ("supported", "verified_within_corpus")

            # get_verification_report
            r = await session.call_tool(
                "get_verification_report", {"project_id": "p1", "report_id": report_id}
            )
            assert json.loads(_text(r))["report_id"] == report_id

            # get_contradictions
            r = await session.call_tool("get_contradictions", {"project_id": "p1"})
            assert json.loads(_text(r))["contradictions"] == []

    asyncio.run(run())


@pytest.mark.skipif(sys.version_info < (3, 11), reason="requires Python 3.11+")
def test_create_claim_denied_without_write(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "qwen_research.mcp"],
        cwd=str(REPO_ROOT),
        env={
            "QWEN_RESEARCH_VERIFICATION_DB": str(tmp_path / "verification.db"),
            # write not enabled → create_claim must be denied.
        },
    )

    async def run() -> None:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            with pytest.raises(Exception) as exc:
                await session.call_tool(
                    "create_claim", {"project_id": "p", "text": "x"}
                )
            assert "permission denied" in str(exc.value)

    asyncio.run(run())
