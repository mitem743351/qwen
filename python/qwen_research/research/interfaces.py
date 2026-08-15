"""The Research Runtime contract and its MCP-facing application contracts.

The Research Runtime is transport-independent: MCP, CLI, API, and dashboard
adapters all call this same surface. ``MCPRequest``/``MCPResult`` are
*application* contracts (not literal MCP wire schemas); the wire adapter is
Phase 2.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable

from qwen_research.claims.models import Claim, ClaimType, QuantitativeClaim, Scope
from qwen_research.claims.relationships import ClaimEvidenceLink, ClaimEvidenceRelationship
from qwen_research.common.ids import ArtifactId, ClaimId, EvidenceId, SessionId, TaskId, WorkflowId
from qwen_research.common.serialization import serializable
from qwen_research.computation.models import (
    ComputationOperation,
    ComputationResult,
    ComputationSummary,
    DatasetProfile,
    DatasetReference,
    ExecutionProfile,
)
from qwen_research.contradictions.models import Contradiction
from qwen_research.domain.artifact import Artifact
from qwen_research.domain.modes import OperatingMode
from qwen_research.domain.reasoning import ReasoningProfile
from qwen_research.domain.research import ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.task import Task
from qwen_research.memory.context import ResearchContext
from qwen_research.memory.models import ResearchMemory, ResearchQuestion
from qwen_research.memory.retriever import MemoryHit
from qwen_research.retrieval.models import DocumentView, SearchOptions, SearchResult
from qwen_research.verification.models import (
    EvidenceAssessment,
    VerificationReport,
    VerificationSummary,
)
from qwen_research.workflows.base import WorkflowResult


@serializable
@dataclasses.dataclass(frozen=True)
class MCPRequest:
    """MCP Server → Research Runtime application request (domain form)."""

    tool: str
    arguments: dict[str, Any]
    session_reference: str | None = None
    caller_identity: str | None = None
    permission_context: tuple[str, ...] = ()


@serializable
@dataclasses.dataclass(frozen=True)
class MCPResult:
    """Research Runtime → MCP Server application result (domain form)."""

    status: str
    result: dict[str, Any] = dataclasses.field(default_factory=dict)
    structured_data: dict[str, Any] | None = None
    artifacts: tuple[ArtifactId, ...] = ()
    citations: tuple[str, ...] = ()
    provenance: dict[str, str] = dataclasses.field(default_factory=dict)
    state_updates: dict[str, Any] = dataclasses.field(default_factory=dict)
    errors: tuple[str, ...] = ()


@runtime_checkable
class ResearchRuntime(Protocol):
    """The public, provider- and transport-independent application contract.

    The concrete implementation (``InMemoryResearchRuntime``) and this protocol
    must agree exactly on every signature.
    """

    def create_session(
        self,
        *,
        project_id: str = "default",
        mode: OperatingMode = OperatingMode.STUDIO_NATIVE,
        metadata: dict[str, str] | None = None,
    ) -> Session: ...

    def get_session(self, session_id: SessionId) -> Session: ...

    def execute_task(
        self,
        description: str,
        *,
        profile: ReasoningProfile | None = None,
        session_id: SessionId | None = None,
    ) -> Task: ...

    def continue_task(self, task_id: TaskId) -> Task: ...

    def inspect_task(self, task_id: TaskId) -> Task: ...

    def retrieve_context(self, task_id: TaskId) -> Any: ...

    def search_corpus(self, query: str, options: SearchOptions | None = None) -> SearchResult: ...

    def get_source(self, document_id: str) -> DocumentView: ...

    def get_project_memory(self, project_id: str, *, limit: int = 10) -> list[MemoryHit]: ...

    def get_research_memory(
        self, project_id: str, query: str | None = None, *, limit: int = 10
    ) -> list[MemoryHit]: ...

    def get_open_questions(self, project_id: str, *, limit: int = 5) -> list[ResearchQuestion]: ...

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
    ) -> ResearchMemory: ...

    def build_research_context(
        self, query: str, *, project_id: str = "default"
    ) -> ResearchContext: ...

    def create_claim(
        self,
        project_id: str,
        text: str,
        *,
        claim_type: ClaimType = ClaimType.UNKNOWN,
        source_refs: tuple[str, ...] = (),
        scope: Scope | None = None,
        quantitative: QuantitativeClaim | None = None,
    ) -> Claim: ...

    def link_claim_evidence(
        self,
        project_id: str,
        claim_id: ClaimId,
        evidence_id: EvidenceId,
        relationship: ClaimEvidenceRelationship,
        rationale: str = "",
    ) -> ClaimEvidenceLink: ...

    def assess_evidence(
        self, project_id: str, claim_id: ClaimId, evidence_id: EvidenceId
    ) -> EvidenceAssessment: ...

    def verify_claim(self, project_id: str, claim_id: ClaimId) -> VerificationReport: ...

    def get_verification_report(self, project_id: str, report_id: str) -> VerificationReport: ...

    def get_project_verification_summaries(
        self, project_id: str
    ) -> list[VerificationSummary]: ...

    def get_contradictions(self, project_id: str) -> list[Contradiction]: ...

    def describe_dataset(self, reference: DatasetReference) -> DatasetProfile: ...

    def run_query(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        query: str,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
    ) -> ComputationResult: ...

    def run_analysis(
        self,
        project_id: str,
        dataset_refs: tuple[DatasetReference, ...],
        operation: ComputationOperation,
        parameters: dict[str, object] | None = None,
        *,
        profile: ExecutionProfile = ExecutionProfile.ANALYTICAL,
        seed: int | None = None,
    ) -> ComputationResult: ...

    def run_python(
        self,
        project_id: str,
        source: str,
        *,
        profile: ExecutionProfile = ExecutionProfile.NUMERICAL,
        seed: int | None = None,
    ) -> ComputationResult: ...

    def get_computation_result(self, project_id: str, computation_id: str) -> ComputationResult: ...

    def get_project_computation_summaries(
        self, project_id: str
    ) -> list[ComputationSummary]: ...

    def run_workflow(self, workflow_id: WorkflowId, task_id: TaskId) -> WorkflowResult: ...

    def get_state(self, task_id: TaskId) -> ResearchState: ...

    def save_artifact(self, artifact: Artifact) -> Artifact: ...

    # -- reserved lifecycle operations (contract only) ---------------------
    # These are declared for contract completeness. The InMemoryResearchRuntime
    # raises UnsupportedOperationError for each — Phase 1 does not implement a
    # pause/resume engine (Phase 1.1).

    def pause_task(self, task_id: TaskId) -> Task: ...

    def resume_task(self, task_id: TaskId) -> Task: ...

    def wait_for_input(self, task_id: TaskId) -> Task: ...

    def provide_input(self, task_id: TaskId, input_data: Any) -> Task: ...

    def cancel_task(self, task_id: TaskId) -> Task: ...
