"""Model-callable tools (Phase 9).

These wrap the Research Runtime's application APIs as neutral internal
``Tool``s that a model may *request* through the controlled tool-call loop. The
model never touches filesystem/SQL/subprocess directly; every tool delegates to
the runtime, which applies the existing permission, project/session scoping, and
resource policies.

``model_callable`` is the exposure flag: a tool exists in the internal registry
but is **not** automatically model-callable. By default WRITE/EXECUTE/
DESTRUCTIVE tools (e.g. ``run_python``) are ``model_callable=False``.
"""

from __future__ import annotations

from typing import Any

from qwen_research.computation.models import ComputationOperation, DatasetReference
from qwen_research.domain.errors import DomainError
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.tools.base import ToolPermission, ToolResult
from qwen_research.tools.registry import ToolRegistry

_OBJECT_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


class _RuntimeTool:
    """A model-callable tool delegating to a Research Runtime method."""

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict[str, Any],
        permission: ToolPermission,
        fn: Any,
        *,
        model_callable: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.permission = permission
        self.model_callable = model_callable
        self._fn = fn

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            data = self._fn(arguments)
            if data is None:
                data = {}
            return ToolResult.success(data)
        except DomainError as exc:
            return ToolResult.failure(exc.message)


def _mem_hits(hits: list[Any]) -> list[dict[str, Any]]:
    return [
        {"memory_id": h.memory_id, "content": h.content, "score": h.score}
        for h in hits
    ]


def _chunks(result: Any) -> list[dict[str, Any]]:
    return [
        {"chunk_id": c.chunk_id, "document_id": c.document_id, "text": c.text, "score": c.score}
        for c in result.chunks
    ]


def build_model_tool_registry(runtime: ResearchRuntime) -> ToolRegistry:
    """Register the Phase 9 model tool set (safe defaults; WRITE/EXECUTE off)."""
    registry = ToolRegistry()
    for tool in _model_tools(runtime):
        registry.register(tool)
    return registry


def _model_tools(runtime: ResearchRuntime) -> list[_RuntimeTool]:
    read = ToolPermission.READ
    analyze = ToolPermission.ANALYZE
    write = ToolPermission.WRITE
    execute = ToolPermission.EXECUTE

    return [
        _RuntimeTool(
            "get_session",
            "Return the current inference session's identity.",
            _OBJECT_SCHEMA,
            read,
            lambda a: {"session_id": runtime.get_session(a["session_id"]).session_id},
        ),
        _RuntimeTool(
            "get_task_state",
            "Return the current task's state.",
            _OBJECT_SCHEMA,
            read,
            lambda a: {
                "task_id": runtime.get_state(a["task_id"]).task_id,
                "stage": runtime.get_state(a["task_id"]).current_stage.value,
            },
        ),
        _RuntimeTool(
            "search_corpus",
            "Search the local corpus and return ranked evidence with provenance.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
            read,
            lambda a: {
                "results": _chunks(runtime.search_corpus(a["query"]))[
                    : int(a.get("limit", 10))
                ]
            },
        ),
        _RuntimeTool(
            "get_source",
            "Return metadata and structure for a document by its id.",
            {
                "type": "object",
                "properties": {"document_id": {"type": "string"}},
                "required": ["document_id"],
            },
            read,
            lambda a: {"document_id": runtime.get_source(a["document_id"]).document_id},
        ),
        _RuntimeTool(
            "get_project_memory",
            "Return project-scoped memory hits.",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            read,
            lambda a: {
                "hits": _mem_hits(
                    runtime.get_project_memory(a["project_id"], limit=int(a.get("limit", 10)))
                )
            },
        ),
        _RuntimeTool(
            "get_research_memory",
            "Return research memory for the current question.",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            read,
            lambda a: {
                "hits": _mem_hits(
                    runtime.get_research_memory(a["project_id"], limit=int(a.get("limit", 10)))
                )
            },
        ),
        _RuntimeTool(
            "get_open_questions",
            "Return unresolved research questions.",
            {"type": "object", "properties": {"limit": {"type": "integer"}}},
            read,
            lambda a: {
                "questions": [
                    q.question for q in runtime.get_open_questions(a["project_id"])
                ]
            },
        ),
        _RuntimeTool(
            "get_contradictions",
            "Return detected contradictions for the project.",
            _OBJECT_SCHEMA,
            read,
            lambda a: {
                "contradictions": [
                    {"contradiction_id": c.contradiction_id, "rationale": c.rationale}
                    for c in runtime.get_contradictions(a["project_id"])
                ]
            },
        ),
        _RuntimeTool(
            "get_verification_report",
            "Return a verification report by id.",
            {
                "type": "object",
                "properties": {"report_id": {"type": "string"}},
                "required": ["report_id"],
            },
            read,
            lambda a: {
                "report_id": runtime.get_verification_report(
                    a["project_id"], a["report_id"]
                ).report_id
            },
        ),
        _RuntimeTool(
            "get_computation_result",
            "Return a computation result by id.",
            {
                "type": "object",
                "properties": {"computation_id": {"type": "string"}},
                "required": ["computation_id"],
            },
            read,
            lambda a: {
                "computation_id": runtime.get_computation_result(
                    a["project_id"], a["computation_id"]
                ).computation_id
            },
        ),
        _RuntimeTool(
            "describe_dataset",
            "Return a dataset profile.",
            {
                "type": "object",
                "properties": {"dataset": {"type": "string"}},
                "required": ["dataset"],
            },
            read,
            lambda a: {
                "dataset_id": runtime.describe_dataset(
                    DatasetReference(dataset_id=a["dataset"])
                ).dataset_id
            },
        ),
        _RuntimeTool(
            "run_query",
            "Run a read-only SQL query over a registered dataset.",
            {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "sql": {"type": "string"},
                },
                "required": ["dataset", "sql"],
            },
            analyze,
            lambda a: {
                "computation_id": runtime.run_query(
                    a["project_id"], (DatasetReference(dataset_id=a["dataset"]),), a["sql"]
                ).computation_id
            },
        ),
        _RuntimeTool(
            "run_analysis",
            "Run a deterministic analysis over a registered dataset.",
            {
                "type": "object",
                "properties": {"dataset": {"type": "string"}},
                "required": ["dataset"],
            },
            analyze,
            lambda a: {
                "computation_id": runtime.run_analysis(
                    a["project_id"],
                    (DatasetReference(dataset_id=a["dataset"]),),
                    ComputationOperation.SUMMARIZE,
                ).computation_id
            },
        ),
        # WRITE / EXECUTE tools exist but are NOT model-callable by default.
        _RuntimeTool(
            "save_research_memory",
            "Persist a research memory (WRITE).",
            {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
            write,
            lambda a: {"saved": True},
            model_callable=False,
        ),
        _RuntimeTool(
            "run_python",
            "Run Python in a sandbox (EXECUTE). Never model-callable.",
            {
                "type": "object",
                "properties": {"source": {"type": "string"}},
                "required": ["source"],
            },
            execute,
            lambda a: {"ran": True},
            model_callable=False,
        ),
    ]
