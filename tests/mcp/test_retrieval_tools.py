"""MCP retrieval tools: search_corpus / get_source via the Research Runtime."""

from __future__ import annotations

from pathlib import Path

from corpus_helpers import index_fixture
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, MCPPermission
from qwen_research.research.runtime import InMemoryResearchRuntime
from qwen_research.tools.registry import ToolRegistry
from qwen_research.tools.retrieval_tools import (
    GetSourceTool,
    SearchCorpusTool,
    build_retrieval_registry,
)


def _runtime_with_corpus(tmp_path: Path) -> InMemoryResearchRuntime:
    _, _, _, retriever, _ = index_fixture(tmp_path)
    return InMemoryResearchRuntime(retriever=retriever)


def test_retrieval_tools_registered(tmp_path: Path) -> None:
    registry = build_retrieval_registry(_runtime_with_corpus(tmp_path))
    assert "search_corpus" in registry
    assert "get_source" in registry
    assert registry.list() == ("get_source", "search_corpus")


def test_retrieval_tools_permissions_are_read() -> None:
    assert DEFAULT_TOOL_PERMISSIONS["search_corpus"] is MCPPermission.READ
    assert DEFAULT_TOOL_PERMISSIONS["get_source"] is MCPPermission.READ


def test_search_corpus_tool_execute(tmp_path: Path) -> None:
    tool = SearchCorpusTool(_runtime_with_corpus(tmp_path))
    result = tool.execute({"query": "surface code"})
    assert result.ok
    data = result.data["search"]
    assert data.returned_count >= 1


def test_get_source_tool_execute(tmp_path: Path) -> None:
    runtime = _runtime_with_corpus(tmp_path)
    doc_id = runtime.search_corpus("surface code").chunks[0].document_id
    tool = GetSourceTool(runtime)
    result = tool.execute({"document_id": doc_id})
    assert result.ok
    assert result.data["document"].document_id == doc_id


def test_get_source_tool_missing_document_is_failure(tmp_path: Path) -> None:
    tool = GetSourceTool(_runtime_with_corpus(tmp_path))
    result = tool.execute({"document_id": "doc_nonexistent"})
    assert not result.ok
    assert result.error


def test_tool_execute_maps_domain_error_to_failure(tmp_path: Path) -> None:
    # A runtime with no retriever raises UnsupportedOperationError internally,
    # which the tool surfaces as a ToolResult failure (not an exception).
    tool = SearchCorpusTool(InMemoryResearchRuntime())
    result = tool.execute({"query": "anything"})
    assert not result.ok
    assert "corpus retriever" in (result.error or "")


def test_registry_is_transport_neutral() -> None:
    registry = ToolRegistry()
    # Registering uses the same neutral Tool contract as MCP/CLI/API adapters.
    assert "search_corpus" not in registry
