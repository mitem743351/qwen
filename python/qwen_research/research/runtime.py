"""In-memory Research Runtime.

Phase 1 provides a minimal but honest runtime: task/session/state/artifact
creation, state-machine advancement, and workflow orchestration. Operations
that depend on unimplemented subsystems (retrieval, verification) raise
:class:`UnsupportedOperationError` rather than returning fabricated results.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from qwen_research.claims.models import Claim, ClaimType, QuantitativeClaim, Scope
from qwen_research.claims.relationships import ClaimEvidenceLink, ClaimEvidenceRelationship
from qwen_research.common.ids import ClaimId, EvidenceId, SessionId, TaskId, WorkflowId
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationResult,
    ComputationSummary,
    DatasetProfile,
    DatasetReference,
    ExecutionProfile,
)
from qwen_research.computation.service import ComputationService
from qwen_research.contradictions.models import Contradiction
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
from qwen_research.memory.context import ContextBudget, ResearchContext, build_context
from qwen_research.memory.models import ResearchMemory, ResearchQuestion
from qwen_research.memory.retriever import MemoryHit
from qwen_research.memory.service import MemoryService
from qwen_research.orchestration.models import (
    ComputationSpec,
    ResearchStatus,
    ResearchTask,
    TaskType,
    WorkflowEvent,
    WorkflowRun,
)
from qwen_research.orchestration.models import (
    ResearchPlan as OrchestrationResearchPlan,
)
from qwen_research.orchestration.service import OrchestrationService
from qwen_research.research.state import (
    InMemoryArtifactStore,
    InMemoryResearchStateStore,
    InMemorySessionStore,
    InMemoryTaskStore,
)
from qwen_research.retrieval.interface import Retriever
from qwen_research.retrieval.models import DocumentView, SearchOptions, SearchResult
from qwen_research.verification.models import (
    EvidenceAssessment,
    VerificationReport,
    VerificationSummary,
)
from qwen_research.verification.service import EvidenceIntegrityService
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
        memory: MemoryService | None = None,
        verification: EvidenceIntegrityService | None = None,
        computation: ComputationService | None = None,
        orchestration: OrchestrationService | None = None,
    ) -> None:
        self._session_store = session_store or InMemorySessionStore()
        self._task_store = task_store or InMemoryTaskStore()
        self._state_store = state_store or InMemoryResearchStateStore()
        self._artifact_store = artifact_store or InMemoryArtifactStore()
        self._workflow_registry = workflow_registry or WorkflowRegistry()
        self._retriever = retriever
        self._memory = memory
        self._verification = verification
        self._computation = computation
        self._orchestration = orchestration

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

    # -- memory ------------------------------------------------------------

    def _require_memory(self) -> MemoryService:
        if self._memory is None:
            raise UnsupportedOperationError("no memory store configured")
        return self._memory

    def get_project_memory(self, project_id: str, *, limit: int = 10) -> list[MemoryHit]:
        return self._require_memory().get_project_memory(project_id, limit=limit)

    def get_research_memory(
        self, project_id: str, query: str | None = None, *, limit: int = 10
    ) -> list[MemoryHit]:
        return self._require_memory().get_research_memory(project_id, query, limit=limit)

    def get_open_questions(self, project_id: str, *, limit: int = 5) -> list[ResearchQuestion]:
        return self._require_memory().get_open_questions(project_id, limit=limit)

    def save_research_memory(
        self,
        project_id: str,
        content: str,
        *,
        source_refs: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        claim_refs: tuple[str, ...] = (),
        computation_refs: tuple[str, ...] = (),
        dataset_refs: tuple[str, ...] = (),
        status: str = "proposed",
        provenance: dict[str, str] | None = None,
    ) -> ResearchMemory:
        return self._require_memory().save_research_memory(
            project_id,
            content,
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            claim_refs=claim_refs,
            computation_refs=computation_refs,
            dataset_refs=dataset_refs,
            status=status,
            provenance=provenance,
        )

    def build_research_context(
        self, query: str, *, project_id: str = "default"
    ) -> ResearchContext:
        """Assemble a bounded evidence + memory context for a query."""
        budget = ContextBudget()
        evidence: list = []
        if self._retriever is not None:
            result = self._retriever.search(
                query, SearchOptions(limit=budget.max_evidence_chunks)
            )
            evidence = list(result.chunks)
        memories: list[MemoryHit] = []
        questions: list[ResearchQuestion] = []
        if self._memory is not None:
            memories = self._memory.search_memory(
                project_id, query, limit=budget.max_memory_items
            )
            questions = self._memory.get_open_questions(
                project_id, limit=budget.max_open_questions
            )
        verification: list[VerificationSummary] = []
        if self._verification is not None:
            verification = self._verification.get_project_verification_summaries(project_id)
        computations: list[ComputationSummary] = []
        if self._computation is not None:
            computations = self._computation.get_computation_summaries(project_id)
        return build_context(
            query,
            evidence=evidence,
            memories=memories,
            open_questions=questions,
            verification=verification,
            computations=computations,
            budget=budget,
        )

    # -- verification / evidence integrity (Phase 5) -----------------------

    def _require_verification(self) -> EvidenceIntegrityService:
        if self._verification is None:
            raise UnsupportedOperationError("no verification service configured")
        return self._verification

    def create_claim(
        self,
        project_id: str,
        text: str,
        *,
        claim_type: ClaimType = ClaimType.UNKNOWN,
        source_refs: tuple[str, ...] = (),
        scope: Scope | None = None,
        quantitative: QuantitativeClaim | None = None,
    ) -> Claim:
        return self._require_verification().create_claim(
            project_id,
            text,
            claim_type=claim_type,
            source_refs=source_refs,
            scope=scope,
            quantitative=quantitative,
        )

    def link_claim_evidence(
        self,
        project_id: str,
        claim_id: ClaimId,
        evidence_id: EvidenceId,
        relationship: ClaimEvidenceRelationship,
        rationale: str = "",
    ) -> ClaimEvidenceLink:
        return self._require_verification().link_claim_evidence(
            project_id, claim_id, evidence_id, relationship, rationale
        )

    def assess_evidence(
        self, project_id: str, claim_id: ClaimId, evidence_id: EvidenceId
    ) -> EvidenceAssessment:
        return self._require_verification().assess_evidence(project_id, claim_id, evidence_id)

    def verify_claim(self, project_id: str, claim_id: ClaimId) -> VerificationReport:
        return self._require_verification().verify_claim(project_id, claim_id)

    def get_verification_report(self, project_id: str, report_id: str) -> VerificationReport:
        return self._require_verification().get_verification_report(project_id, report_id)

    def get_project_verification_summaries(self, project_id: str) -> list[VerificationSummary]:
        return self._require_verification().get_project_verification_summaries(project_id)

    def get_contradictions(self, project_id: str) -> list[Contradiction]:
        return self._require_verification().get_contradictions(project_id)

    # -- research orchestration (Phase 7) ----------------------------------

    def _require_orchestration(self) -> OrchestrationService:
        if self._orchestration is None:
            raise UnsupportedOperationError("no orchestration service configured")
        return self._orchestration

    def plan_research(
        self,
        description: str,
        *,
        project_id: str = "default",
        session_id: str = "default",
        task_type: TaskType | None = None,
        profile: str = "DEEP",
        subquestions: tuple[str, ...] = (),
        computation: ComputationSpec | None = None,
    ) -> tuple[ResearchTask, OrchestrationResearchPlan]:
        return self._require_orchestration().plan_research(
            description,
            project_id=project_id,
            session_id=session_id,
            task_type=task_type,
            profile=profile,
            subquestions=subquestions,
            computation=computation,
        )

    def start_research(self, plan_id: str) -> WorkflowRun:
        return self._require_orchestration().start_research(plan_id)

    def get_research_status(self, run_id: str) -> ResearchStatus:
        return self._require_orchestration().get_research_status(run_id)

    def pause_research(self, run_id: str) -> WorkflowRun:
        return self._require_orchestration().pause_research(run_id)

    def resume_research(self, run_id: str) -> WorkflowRun:
        return self._require_orchestration().resume_research(run_id)

    def cancel_research(self, run_id: str) -> WorkflowRun:
        return self._require_orchestration().cancel_research(run_id)

    def get_research_summary(self, run_id: str) -> dict[str, object]:
        return self._require_orchestration().get_research_summary(run_id)

    def get_research_plan(self, plan_id: str) -> OrchestrationResearchPlan:
        return self._require_orchestration().get_plan(plan_id)

    def get_research_events(self, run_id: str) -> list[WorkflowEvent]:
        return self._require_orchestration().get_events(run_id)

    # -- deterministic computation (Phase 6) -------------------------------

    def _require_computation(self) -> ComputationService:
        if self._computation is None:
            raise UnsupportedOperationError("no computation service configured")
        return self._computation

    def describe_dataset(self, reference: DatasetReference) -> DatasetProfile:
        return self._require_computation().describe_dataset(reference)

    def run_query(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        query: str,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
    ) -> ComputationResult:
        return self._require_computation().run_query(
            project_id, dataset_refs, query, parameters, profile=profile
        )

    def run_analysis(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        operation: ComputationOperation,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
        seed: int | None = None,
    ) -> ComputationResult:
        return self._require_computation().run_analysis(
            project_id, dataset_refs, operation, parameters, profile=profile, seed=seed
        )

    def run_python(
        self,
        project_id: str,
        source: str,
        *,
        profile: ExecutionProfile = ExecutionProfile.NUMERICAL,
        seed: int | None = None,
    ) -> ComputationResult:
        return self._require_computation().run_python(
            project_id, source, profile=profile, seed=seed
        )

    def get_computation_result(
        self, project_id: str, computation_id: str
    ) -> ComputationResult:
        return self._require_computation().get_computation_result(project_id, computation_id)

    def get_project_computation_summaries(
        self, project_id: str
    ) -> list[ComputationSummary]:
        return self._require_computation().get_computation_summaries(project_id)

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
