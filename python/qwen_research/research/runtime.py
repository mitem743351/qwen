"""In-memory Research Runtime.

Phase 1 provides a minimal but honest runtime: task/session/state/artifact
creation, state-machine advancement, and workflow orchestration. Operations
that depend on unimplemented subsystems (retrieval, verification) raise
:class:`UnsupportedOperationError` rather than returning fabricated results.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from qwen_research.common.ids import ClaimId, SessionId, TaskId, WorkflowId
from qwen_research.domain.artifact import Artifact
from qwen_research.domain.errors import (
    DocumentNotFoundError,
    PersistenceError,
    UnsupportedOperationError,
)
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import DEEP, ReasoningProfile
from qwen_research.domain.research import ResearchPlan, ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task, TaskStatus, next_active_status
from qwen_research.domain.verification import VerificationResult
from qwen_research.research.state import (
    InMemoryArtifactStore,
    InMemoryResearchStateStore,
    InMemorySessionStore,
    InMemoryTaskStore,
)
from qwen_research.retrieval.interface import Retriever
from qwen_research.retrieval.models import DocumentView, SearchOptions, SearchResult
from qwen_research.workflows.base import WorkflowContext, WorkflowResult
from qwen_research.workflows.registry import WorkflowRegistry


class InMemoryResearchRuntime:
    """A transport-independent Research Runtime backed by in-memory stores."""

    def __init__(
        self,
        *,
        session_store: InMemorySessionStore | None = None,
        task_store: InMemoryTaskStore | None = None,
        state_store: InMemoryResearchStateStore | None = None,
        artifact_store: InMemoryArtifactStore | None = None,
        workflow_registry: WorkflowRegistry | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self._session_store = session_store or InMemorySessionStore()
        self._task_store = task_store or InMemoryTaskStore()
        self._state_store = state_store or InMemoryResearchStateStore()
        self._artifact_store = artifact_store or InMemoryArtifactStore()
        self._workflow_registry = workflow_registry or WorkflowRegistry()
        self._retriever = retriever

    # -- sessions ---------------------------------------------------------

    def create_session(
        self,
        *,
        project_id: str = "default",
        mode: OperatingMode = OperatingMode.STUDIO_NATIVE,
        metadata: dict[str, str] | None = None,
    ) -> Session:
        session = Session.create(project_id=project_id, mode=mode, metadata=metadata)
        self._session_store.save(session)
        return session

    def get_session(self, session_id: SessionId) -> Session:
        session = self._session_store.get(session_id)
        if session is None:
            raise PersistenceError(f"no session with id {session_id!r}")
        return session

    # -- tasks ------------------------------------------------------------

    def execute_task(
        self,
        description: str,
        *,
        profile: ReasoningProfile | None = None,
        session_id: SessionId | None = None,
    ) -> Task:
        """Create, classify, and plan a task (contract demonstration only)."""
        profile = profile or DEEP
        if session_id is None:
            session_id = self.create_session().session_id
        else:
            # Validate that the requested session exists (session/task isolation).
            self.get_session(session_id)

        task = Task.create(description, session_id, profile.name)
        self._task_store.save(task)

        task = task.transition(TaskStatus.CLASSIFIED)
        self._task_store.save(task)

        task = task.transition(TaskStatus.PLANNED)
        self._task_store.save(task)

        plan = ResearchPlan(steps=("plan", "retrieve", "reason", "verify", "synthesize"))
        self._state_store.save(ResearchState.create(task.task_id, plan=plan))
        return task

    def continue_task(self, task_id: TaskId) -> Task:
        """Advance the task one step along the active progression."""
        task = self._require_task(task_id)
        next_status = next_active_status(task.status)
        if next_status is None:
            return task  # terminal or control state: nothing to advance
        task = task.transition(next_status)
        self._task_store.save(task)
        self._sync_stage(task)
        return task

    def inspect_task(self, task_id: TaskId) -> Task:
        return self._require_task(task_id)

    def get_state(self, task_id: TaskId) -> ResearchState:
        state = self._state_store.get(task_id)
        if state is None:
            raise PersistenceError(f"no research state for task {task_id!r}")
        return state

    # -- workflows --------------------------------------------------------

    def run_workflow(self, workflow_id: WorkflowId, task_id: TaskId) -> WorkflowResult:
        workflow = self._workflow_registry.get(workflow_id)
        task = self._require_task(task_id)
        context = WorkflowContext(
            workflow_id=workflow_id, task_id=task_id, session_id=task.session_id
        )
        return workflow.start(context)

    # -- artifacts --------------------------------------------------------

    def save_artifact(self, artifact: Artifact) -> Artifact:
        self._artifact_store.save(artifact)
        if artifact.task_id is not None:
            state = self._state_store.get(artifact.task_id)
            if state is not None:
                self._state_store.save(
                    dataclasses.replace(
                        state, artifact_refs=state.artifact_refs + (artifact.artifact_id,)
                    )
                )
        return artifact

    # -- not-yet-implemented capabilities ---------------------------------

    def retrieve_context(self, task_id: TaskId) -> Any:
        raise UnsupportedOperationError("retrieval is not implemented until Phase 3")

    def search_corpus(self, query: str, options: SearchOptions | None = None) -> SearchResult:
        """Search the local corpus and return ranked, citable evidence."""
        if self._retriever is None:
            raise UnsupportedOperationError("no corpus retriever configured")
        return self._retriever.search(query, options)

    def get_source(self, document_id: str) -> DocumentView:
        """Return document metadata and structure for a source id."""
        if self._retriever is None:
            raise UnsupportedOperationError("no corpus retriever configured")
        view = self._retriever.get_document(document_id)
        if view is None:
            raise DocumentNotFoundError(f"document {document_id!r} not found")
        return view

    def verify_claim(self, claim_id: ClaimId) -> VerificationResult:
        raise UnsupportedOperationError("verification is not implemented until Phase 6")

    # -- reserved lifecycle operations (contract only) --------------------
    # The domain supports PAUSED / WAITING / NEEDS_INPUT / CANCELLED as valid
    # states, but the runtime does not yet operate a pause/resume engine. These
    # operations raise UnsupportedOperationError rather than returning fake
    # success (Phase 1.1).

    def pause_task(self, task_id: TaskId) -> Task:
        raise UnsupportedOperationError("pause_task is not implemented (reserved lifecycle)")

    def resume_task(self, task_id: TaskId) -> Task:
        raise UnsupportedOperationError("resume_task is not implemented (reserved lifecycle)")

    def wait_for_input(self, task_id: TaskId) -> Task:
        raise UnsupportedOperationError("wait_for_input is not implemented (reserved lifecycle)")

    def provide_input(self, task_id: TaskId, input_data: Any) -> Task:
        raise UnsupportedOperationError("provide_input is not implemented (reserved lifecycle)")

    def cancel_task(self, task_id: TaskId) -> Task:
        raise UnsupportedOperationError("cancel_task is not implemented (reserved lifecycle)")

    # -- helpers ----------------------------------------------------------

    def _require_task(self, task_id: TaskId) -> Task:
        task = self._task_store.get(task_id)
        if task is None:
            raise PersistenceError(f"no task with id {task_id!r}")
        return task

    def _sync_stage(self, task: Task) -> None:
        state = self._state_store.get(task.task_id)
        if state is not None:
            self._state_store.save(dataclasses.replace(state, current_stage=task.status))


def runtime_with_stores(
    *,
    session_store: InMemorySessionStore,
    task_store: InMemoryTaskStore,
    state_store: InMemoryResearchStateStore,
    artifact_store: InMemoryArtifactStore,
    workflow_registry: WorkflowRegistry,
) -> InMemoryResearchRuntime:
    """Construct a runtime from explicit store instances (test convenience)."""
    return InMemoryResearchRuntime(
        session_store=session_store,
        task_store=task_store,
        state_store=state_store,
        artifact_store=artifact_store,
        workflow_registry=workflow_registry,
    )
