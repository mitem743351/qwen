"""Internal retrieval tools (registered in the Tool Registry).

Neutral, transport-independent implementations of the ``search_corpus`` and
``get_source`` capabilities, wrapping the Research Runtime (which wraps the
Retriever → Index). The MCP layer exposes the same capabilities as thin typed
adapters. No filesystem or SQL access, and no MCP import, lives here.
"""

from __future__ import annotations

from typing import Any

from qwen_research.domain.errors import DomainError
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.retrieval.models import SearchOptions
from qwen_research.tools.base import ToolPermission, ToolResult
from qwen_research.tools.registry import ToolRegistry


class SearchCorpusTool:
    name = "search_corpus"
    description = "Search the local corpus and return ranked evidence with provenance."
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "roots": {"type": "array", "items": {"type": "string"}},
            "document_types": {"type": "array", "items": {"type": "string"}},
            "path_prefix": {"type": "string"},
        },
        "required": ["query"],
    }
    permission = ToolPermission.READ

    def __init__(self, runtime: ResearchRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = self._runtime.search_corpus(
                arguments["query"],
                SearchOptions(
                    limit=int(arguments.get("limit", 10)),
                    roots=tuple(arguments.get("roots") or ()),
                    document_types=tuple(arguments.get("document_types") or ()),
                    path_prefix=arguments.get("path_prefix"),
                ),
            )
            return ToolResult.success({"search": result})
        except DomainError as exc:
            return ToolResult.failure(exc.message)


class GetSourceTool:
    name = "get_source"
    description = "Return metadata and structure for a document by its id."
    schema = {
        "type": "object",
        "properties": {"document_id": {"type": "string"}},
        "required": ["document_id"],
    }
    permission = ToolPermission.READ

    def __init__(self, runtime: ResearchRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            view = self._runtime.get_source(arguments["document_id"])
            return ToolResult.success({"document": view})
        except DomainError as exc:
            return ToolResult.failure(exc.message)


def build_retrieval_registry(runtime: ResearchRuntime) -> ToolRegistry:
    """Register the Phase 3 retrieval tools in an internal Tool Registry."""
    registry = ToolRegistry()
    registry.register(SearchCorpusTool(runtime))
    registry.register(GetSourceTool(runtime))
    return registry
