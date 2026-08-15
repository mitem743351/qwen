"""The MCP server — a thin external adapter over the Research Runtime.

Owns: protocol handling, tool registration, request validation, permission
checks, schema translation, error normalization, transport, and lifecycle.

Does **not** own: research planning, reasoning profiles, retrieval, memory,
verification, workflow logic, provider selection, or provider API calls. The
Research Runtime and Domain layers have no dependency on this module.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer as SDKMCPServer
from mcp.shared.exceptions import MCPError

from qwen_research.claims.models import ClaimType
from qwen_research.claims.relationships import ClaimEvidenceRelationship
from qwen_research.common.ids import ClaimId, EvidenceId, SessionId, TaskId
from qwen_research.computation.models import ComputationOperation
from qwen_research.domain.errors import ConfigurationError, PermissionError
from qwen_research.mcp.adapters import SchemaAdapter
from qwen_research.mcp.config import MCPServerConfig
from qwen_research.mcp.errors import map_error
from qwen_research.mcp.permissions import DEFAULT_TOOL_PERMISSIONS, ToolPermissionPolicy
from qwen_research.mcp.schemas import (
    DEFAULT_TOOLS,
    TOOL_DESCRIPTIONS,
    ClaimEvidenceRelationshipParam,
    ClaimIdParam,
    ClaimTypeParam,
    ComputationIdParam,
    ComputationOperationParam,
    ContentParam,
    DatasetRefParam,
    DatasetRefsParam,
    DescriptionParam,
    DocumentIdParam,
    DocumentTypesParam,
    EvidenceIdParam,
    LexicalKParam,
    LimitParam,
    MaxChunksPerDocumentParam,
    MetadataParam,
    ModeParam,
    OptionalQueryParam,
    OptionalSessionIdParam,
    ParametersParam,
    PathPrefixParam,
    ProjectIdParam,
    PythonSourceParam,
    QueryParam,
    QuerySqlParam,
    RationaleParam,
    ReasoningProfileParam,
    ReportIdParam,
    ResearchIdParam,
    RetrievalModeParam,
    RootsParam,
    SeedParam,
    SemanticKParam,
    SessionIdParam,
    StatusParam,
    StringListParam,
    SubquestionsParam,
    TaskIdParam,
    TaskTypeParam,
)
from qwen_research.mcp.transport import MCPTransport, create_transport
from qwen_research.orchestration.models import TaskType
from qwen_research.research.interfaces import ResearchRuntime
from qwen_research.retrieval.models import RetrievalMode, SearchOptions

logger = logging.getLogger("qwen_research.mcp")

T = TypeVar("T")


def guarded_call(
    policy: ToolPermissionPolicy,
    tool_name: str,
    fn: Callable[[], T],
) -> T:
    """Enforce permissions and map internal errors to safe MCP errors.

    Raises :class:`MCPError` for permission denials and for any internal
    exception (mapped via :func:`map_error`). Never leaks tracebacks or
    secrets.
    """
    required = policy.tool_required(tool_name)
    if not policy.allows(tool_name):
        info = map_error(
            PermissionError(f"tool {tool_name!r} requires {required.value!r} permission")
        )
        raise MCPError(code=info.code, message=info.message, data={"category": info.category})
    try:
        return fn()
    except MCPError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize every internal error
        info = map_error(exc)
        raise MCPError(
            code=info.code, message=info.message, data={"category": info.category}
        ) from None


class MCPServerApp:
    """The MCP server application: SDK server + tools + lifecycle."""

    def __init__(
        self,
        runtime: ResearchRuntime,
        config: MCPServerConfig | None = None,
        transport: MCPTransport | None = None,
    ) -> None:
        self._runtime = runtime
        self._config = config or MCPServerConfig()
        self._adapter = SchemaAdapter()
        self._policy = ToolPermissionPolicy.from_config(
            self._config.permissions, DEFAULT_TOOL_PERMISSIONS
        )
        self._transport = transport or create_transport(self._config.transport)
        self._status = "initialized"
        self._server = self._build_server()

    # -- lifecycle --------------------------------------------------------

    @property
    def status(self) -> str:
        return self._status

    def serve(self) -> None:
        """Run the server over its transport (blocking)."""
        self._status = "serving"
        logger.info(
            "MCP server starting (name=%s transport=%s)",
            self._config.name,
            self._config.transport,
        )
        try:
            self._transport.serve(self._server)
        finally:
            self._status = "stopped"
            logger.info("MCP server stopped")

    def shutdown(self) -> None:
        """Request graceful shutdown."""
        self._transport.shutdown()
        self._status = "stopped"
        logger.info("MCP server shutdown requested")

    # -- diagnostics ------------------------------------------------------

    def _build_catalog(self, tools: list[Any]) -> dict[str, dict[str, Any]]:
        """Project SDK tool descriptors into the catalog dict."""
        return {
            tool.name: {"description": tool.description, "input_schema": tool.input_schema}
            for tool in tools
        }

    async def tool_catalog_async(self) -> dict[str, dict[str, Any]]:
        """Return the authoritative MCP wire tool surface (awaitable).

        Use this from within a running event loop (``await app.tool_catalog_async()``).
        """
        return self._build_catalog(await self._server.list_tools())

    def tool_catalog(self) -> dict[str, dict[str, Any]]:
        """Return the authoritative MCP wire tool surface (sync).

        Keys are tool names; values carry the tool's ``description`` and
        ``input_schema`` exactly as the SDK exposes them on the wire. This is
        the single source of truth for tests and diagnostics — there is no
        parallel hand-written schema to drift.

        This method is synchronous and drives its own event loop via
        ``asyncio.run``. If a running event loop exists (e.g. inside an async
        tool handler or a client callback), call
        :meth:`tool_catalog_async` instead; calling this method there raises a
        clear ``RuntimeError`` rather than the ambiguous
        ``asyncio.run() cannot be called from a running event loop``.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "tool_catalog() is synchronous and cannot be used inside a "
                "running event loop; await tool_catalog_async() instead"
            )
        return asyncio.run(self.tool_catalog_async())

    def list_tools(self) -> list[str]:
        """Return the registered tool names (derived from the wire catalog)."""
        return sorted(self.tool_catalog())

    def diagnostics(self) -> dict[str, Any]:
        """Minimal local diagnostics (no sensitive data)."""
        return {
            "server": self._config.name,
            "version": self._config.version,
            "transport": self._config.transport,
            "status": self._status,
            "registered_tools": self.list_tools(),
            "runtime_status": "ok",
        }

    # -- server construction ----------------------------------------------

    def _build_server(self) -> SDKMCPServer:
        server = SDKMCPServer(name=self._config.name, version=self._config.version)
        adapter = self._adapter
        runtime = self._runtime
        policy = self._policy

        def get_session(session_id: SessionIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                session = runtime.get_session(SessionId(session_id))
                return adapter.session_result(session)

            return guarded_call(policy, "get_session", run)

        def create_session(
            project_id: ProjectIdParam = "default",
            mode: ModeParam = "studio_native",
            metadata: MetadataParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                session = runtime.create_session(
                    project_id=project_id,
                    mode=adapter.mode(mode),
                    metadata=adapter.metadata(metadata),
                )
                return adapter.session_result(session)

            return guarded_call(policy, "create_session", run)

        def execute_task(
            description: DescriptionParam,
            session_id: OptionalSessionIdParam = None,
            reasoning_profile: ReasoningProfileParam = "DEEP",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.execute_task(
                    description,
                    profile=adapter.profile(reasoning_profile),
                    session_id=SessionId(session_id) if session_id else None,
                )
                return adapter.task_result(task)

            return guarded_call(policy, "execute_task", run)

        def continue_task(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.continue_task(TaskId(task_id))
                return adapter.task_result(task)

            return guarded_call(policy, "continue_task", run)

        def get_task_state(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task = runtime.inspect_task(TaskId(task_id))
                return adapter.task_result(task)

            return guarded_call(policy, "get_task_state", run)

        def get_research_state(task_id: TaskIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                state = runtime.get_state(TaskId(task_id))
                return adapter.research_state_result(state)

            return guarded_call(policy, "get_research_state", run)

        def search_corpus(
            query: QueryParam,
            limit: LimitParam = 10,
            roots: RootsParam = None,
            document_types: DocumentTypesParam = None,
            path_prefix: PathPrefixParam = None,
            mode: RetrievalModeParam = "hybrid",
            lexical_k: LexicalKParam = 20,
            semantic_k: SemanticKParam = 20,
            max_chunks_per_document: MaxChunksPerDocumentParam = 3,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                result = runtime.search_corpus(
                    query,
                    SearchOptions(
                        limit=limit,
                        roots=tuple(roots or ()),
                        document_types=tuple(document_types or ()),
                        path_prefix=path_prefix,
                        mode=RetrievalMode(mode),
                        lexical_k=lexical_k,
                        semantic_k=semantic_k,
                        max_chunks_per_document=max_chunks_per_document,
                    ),
                )
                return adapter.search_result(result)

            return guarded_call(policy, "search_corpus", run)

        def get_source(document_id: DocumentIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                view = runtime.get_source(document_id)
                return adapter.document_view_result(view)

            return guarded_call(policy, "get_source", run)

        def get_project_memory(
            project_id: ProjectIdParam = "default",
            limit: LimitParam = 10,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                hits = runtime.get_project_memory(project_id, limit=limit)
                return adapter.memory_hits_result(hits)

            return guarded_call(policy, "get_project_memory", run)

        def get_research_memory(
            project_id: ProjectIdParam = "default",
            query: OptionalQueryParam = None,
            limit: LimitParam = 10,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                hits = runtime.get_research_memory(project_id, query, limit=limit)
                return adapter.memory_hits_result(hits)

            return guarded_call(policy, "get_research_memory", run)

        def get_open_questions(
            project_id: ProjectIdParam = "default",
            limit: LimitParam = 5,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                questions = runtime.get_open_questions(project_id, limit=limit)
                return adapter.research_questions_result(questions)

            return guarded_call(policy, "get_open_questions", run)

        def save_research_memory(
            content: ContentParam,
            project_id: ProjectIdParam = "default",
            source_refs: StringListParam = None,
            evidence_refs: StringListParam = None,
            claim_refs: StringListParam = None,
            status: StatusParam = "proposed",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                memory = runtime.save_research_memory(
                    project_id,
                    content,
                    source_refs=tuple(source_refs or ()),
                    evidence_refs=tuple(evidence_refs or ()),
                    claim_refs=tuple(claim_refs or ()),
                    status=status or "proposed",
                )
                return adapter.research_memory_result(memory)

            return guarded_call(policy, "save_research_memory", run)

        def create_claim(
            text: ContentParam,
            project_id: ProjectIdParam = "default",
            claim_type: ClaimTypeParam = "unknown",
            source_refs: StringListParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                claim = runtime.create_claim(
                    project_id,
                    text,
                    claim_type=ClaimType(claim_type),
                    source_refs=tuple(source_refs or ()),
                )
                return adapter.claim_result(claim)

            return guarded_call(policy, "create_claim", run)

        def link_claim_evidence(
            claim_id: ClaimIdParam,
            evidence_id: EvidenceIdParam,
            relationship: ClaimEvidenceRelationshipParam,
            project_id: ProjectIdParam = "default",
            rationale: RationaleParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                link = runtime.link_claim_evidence(
                    project_id,
                    ClaimId(claim_id),
                    EvidenceId(evidence_id),
                    ClaimEvidenceRelationship(relationship),
                    rationale or "",
                )
                return adapter.claim_evidence_link_result(link)

            return guarded_call(policy, "link_claim_evidence", run)

        def assess_evidence(
            claim_id: ClaimIdParam,
            evidence_id: EvidenceIdParam,
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                assessment = runtime.assess_evidence(
                    project_id, ClaimId(claim_id), EvidenceId(evidence_id)
                )
                return adapter.evidence_assessment_result(assessment)

            return guarded_call(policy, "assess_evidence", run)

        def verify_claim(
            claim_id: ClaimIdParam,
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                report = runtime.verify_claim(project_id, ClaimId(claim_id))
                return adapter.verification_report_result(report)

            return guarded_call(policy, "verify_claim", run)

        def get_verification_report(
            report_id: ReportIdParam,
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                report = runtime.get_verification_report(project_id, report_id)
                return adapter.verification_report_result(report)

            return guarded_call(policy, "get_verification_report", run)

        def get_contradictions(
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                contradictions = runtime.get_contradictions(project_id)
                return adapter.contradictions_result(contradictions)

            return guarded_call(policy, "get_contradictions", run)

        def describe_dataset(dataset: DatasetRefParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                profile = runtime.describe_dataset(adapter.dataset_reference(dataset))
                return adapter.dataset_profile_result(profile)

            return guarded_call(policy, "describe_dataset", run)

        def run_query(
            query: QuerySqlParam,
            datasets: DatasetRefsParam = None,
            parameters: ParametersParam = None,
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                refs = tuple(adapter.dataset_reference(d) for d in (datasets or []))
                result = runtime.run_query(project_id, refs, query, parameters or {})
                return adapter.computation_result_result(result)

            return guarded_call(policy, "run_query", run)

        def run_analysis(
            operation: ComputationOperationParam,
            datasets: DatasetRefsParam = None,
            parameters: ParametersParam = None,
            project_id: ProjectIdParam = "default",
            seed: SeedParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                refs = tuple(adapter.dataset_reference(d) for d in (datasets or []))
                result = runtime.run_analysis(
                    project_id,
                    refs,
                    ComputationOperation(operation),
                    parameters or {},
                    seed=seed,
                )
                return adapter.computation_result_result(result)

            return guarded_call(policy, "run_analysis", run)

        def get_computation_result(
            computation_id: ComputationIdParam,
            project_id: ProjectIdParam = "default",
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                result = runtime.get_computation_result(project_id, computation_id)
                return adapter.computation_result_result(result)

            return guarded_call(policy, "get_computation_result", run)

        def run_python(
            source: PythonSourceParam,
            project_id: ProjectIdParam = "default",
            seed: SeedParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                result = runtime.run_python(project_id, source, seed=seed)
                return adapter.computation_result_result(result)

            return guarded_call(policy, "run_python", run)

        def plan_research(
            description: DescriptionParam,
            project_id: ProjectIdParam = "default",
            task_type: TaskTypeParam = None,
            reasoning_profile: ReasoningProfileParam = "DEEP",
            subquestions: SubquestionsParam = None,
        ) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                task, plan = runtime.plan_research(
                    description,
                    project_id=project_id,
                    task_type=TaskType(task_type) if task_type else None,
                    profile=reasoning_profile,
                    subquestions=tuple(subquestions or ()),
                )
                return adapter.plan_result(task, plan)

            return guarded_call(policy, "plan_research", run)

        def start_research(plan_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return adapter.run_result(runtime.start_research(plan_id))

            return guarded_call(policy, "start_research", run)

        def get_research_status(run_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return adapter.research_status_result(runtime.get_research_status(run_id))

            return guarded_call(policy, "get_research_status", run)

        def pause_research(run_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return adapter.run_result(runtime.pause_research(run_id))

            return guarded_call(policy, "pause_research", run)

        def resume_research(run_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return adapter.run_result(runtime.resume_research(run_id))

            return guarded_call(policy, "resume_research", run)

        def cancel_research(run_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return adapter.run_result(runtime.cancel_research(run_id))

            return guarded_call(policy, "cancel_research", run)

        def get_research_summary(run_id: ResearchIdParam) -> dict[str, Any]:
            def run() -> dict[str, Any]:
                return runtime.get_research_summary(run_id)

            return guarded_call(policy, "get_research_summary", run)

        handlers: dict[str, Callable[..., Any]] = {
            "get_session": get_session,
            "create_session": create_session,
            "execute_task": execute_task,
            "continue_task": continue_task,
            "get_task_state": get_task_state,
            "get_research_state": get_research_state,
            "search_corpus": search_corpus,
            "get_source": get_source,
            "get_project_memory": get_project_memory,
            "get_research_memory": get_research_memory,
            "get_open_questions": get_open_questions,
            "save_research_memory": save_research_memory,
            "create_claim": create_claim,
            "link_claim_evidence": link_claim_evidence,
            "assess_evidence": assess_evidence,
            "verify_claim": verify_claim,
            "get_verification_report": get_verification_report,
            "get_contradictions": get_contradictions,
            "describe_dataset": describe_dataset,
            "run_query": run_query,
            "run_analysis": run_analysis,
            "get_computation_result": get_computation_result,
            "run_python": run_python,
            "plan_research": plan_research,
            "start_research": start_research,
            "get_research_status": get_research_status,
            "pause_research": pause_research,
            "resume_research": resume_research,
            "cancel_research": cancel_research,
            "get_research_summary": get_research_summary,
        }

        enabled = self._config.enabled_tools or DEFAULT_TOOLS
        for name in enabled:
            if name not in handlers:
                raise ConfigurationError(f"unknown MCP tool {name!r}")
            server.add_tool(handlers[name], name=name, description=TOOL_DESCRIPTIONS[name])

        return server


def run_stdio_server(runtime: ResearchRuntime, config: MCPServerConfig | None = None) -> None:
    """Convenience: build and serve the MCP server over stdio (blocking)."""
    MCPServerApp(runtime, config).serve()


__all__ = ["MCPServerApp", "guarded_call", "run_stdio_server"]
