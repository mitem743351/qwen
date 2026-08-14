# Runtime Contracts

The application-layer contracts implemented in Phase 1: the Research Runtime,
the MCP application contracts, the internal Tool Registry, the Workflow
contracts, the Inference Provider protocol, and the persistence interfaces.

---

## Research Runtime

```text
ResearchRuntime (protocol, research/interfaces.py)
    create_session(*, project_id="default", mode=STUDIO_NATIVE) -> Session
    execute_task(description, *, profile=None, session_id=None) -> Task
    continue_task(task_id) -> Task
    inspect_task(task_id) -> Task
    retrieve_context(task_id)   # UnsupportedOperationError until Phase 3
    verify_claim(claim_id) -> VerificationReport
    run_workflow(workflow_id, task_id) -> WorkflowResult
    get_state(task_id) -> ResearchState
    save_artifact(artifact) -> Artifact

    # Reserved lifecycle operations (contract only; Phase 1.1)
    pause_task(task_id)           # UnsupportedOperationError
    resume_task(task_id)          # UnsupportedOperationError
    wait_for_input(task_id)       # UnsupportedOperationError
    provide_input(task_id, data)  # UnsupportedOperationError
    cancel_task(task_id)          # UnsupportedOperationError
```

`InMemoryResearchRuntime` (`research/runtime.py`) implements this over
in-memory stores. The **protocol and implementation agree exactly** on every
signature (statically enforced by mypy via a conformance test).

- `create_session` accepts an operating `mode` (first-class since Phase 0.5)
  and a `project_id`.
- `execute_task` accepts an optional `session_id` to run within an existing
  session; otherwise it auto-creates one. It creates, classifies, and plans the
  task and creates a `ResearchState`.
- `continue_task` advances one step along the active execution progression.
- `retrieve_context` raises `UnsupportedOperationError` (no fabricated results —
  B23). `verify_claim` and the other verification methods delegate to a
  configured `EvidenceIntegrityService` (Phase 5); when no verification service
  is configured they raise `UnsupportedOperationError` (B23).

### Retrieval (Phase 3–4)

`search_corpus(query, options)` delegates to the configured `Retriever`
(lexical, semantic, or hybrid). `get_source(document_id)` returns document
metadata. No SQLite/FTS/vector objects reach the runtime — only `Retriever` and
`SearchOptions`/`SearchResult`.

### Memory (Phase 4)

`get_project_memory` / `get_research_memory` / `get_open_questions` /
`save_research_memory` delegate to a `MemoryService` (which wraps the neutral
repository interfaces). `build_research_context(query, project_id=…)` assembles
a bounded `ResearchContext` of evidence + memory + open questions.

### Memory provenance (Phase 4.1)

`save_research_memory` validates research-derived references (project-scoped)
via a configured `ProvenanceValidator` **before** the write commits; an
unresolved reference raises `ProvenanceError` and nothing is persisted. This
holds for every writer (MCP, CLI, API, workflow), not only MCP.

### Verification (Phase 5)

`create_claim`, `link_claim_evidence`, `assess_evidence`, `verify_claim`,
`get_verification_report`, and `get_contradictions` delegate to a configured
`EvidenceIntegrityService` (over a `VerificationStore` + optional `CorpusIndex`).
`verify_claim` returns a persisted `VerificationReport` and updates the claim's
memory-promotion status; without a verification service, these operations raise
`UnsupportedOperationError`.

### Reserved lifecycle operations

`pause_task`, `resume_task`, `wait_for_input`, `provide_input`, and
`cancel_task` are declared on the protocol for contract completeness. The
domain model supports `PAUSED` / `WAITING` / `NEEDS_INPUT` / `CANCELLED` as
valid states, but **Phase 1 does not implement a pause/resume engine** — these
operations raise `UnsupportedOperationError` rather than returning fake
success.

---

## MCP application contracts

`MCPRequest` / `MCPResult` (`research/interfaces.py`) are **domain/application**
contracts, not literal MCP wire schemas. The wire adapter is Phase 2.

```text
MCPRequest   tool, arguments, session_reference, caller_identity, permission_context
MCPResult    status, result, structured_data, artifacts, citations,
             provenance, state_updates, errors
```

---

## Internal Tool Registry

```text
Tool (tools/base.py)     name, description, schema, permission, execute()
ToolResult               ok, data, error
ToolRegistry (registry)  register(), unregister(), get(), list()
```

Transport-independent (ADR 0020): MCP is one adapter over this registry.
`require_permission`/`invoke` enforce the permission class and normalize
failures.

---

## Workflow contracts

```text
Workflow (workflows/base.py)  start(), continue_(), pause(), resume(), cancel()
WorkflowContext               workflow_id, task_id, session_id, metadata
WorkflowResult                status, workflow_id, task_id, data, error
WorkflowStatus                STARTED/RUNNING/PAUSED/RESUMED/COMPLETED/CANCELLED/FAILED
WorkflowRegistry              register(), unregister(), get(), list()
```

Deep-research workflows are **not** implemented; the contract is exercised by a
placeholder workflow in tests.

---

## Inference Provider protocol

```text
InferenceProvider (inference/interfaces.py)
    capabilities()
    model_info()
    generate()
    stream()
    structured_output()
```

No provider implementation, no network access. The Research Runtime depends
only on this protocol; provider specifics live in the Inference Runtime
(Phase 8).

---

## Persistence interfaces

```text
SessionRepository, TaskRepository, ResearchStateRepository, ArtifactRepository
(persistence/interfaces.py)
```

Protocols only. In-memory implementations in `research/state.py`
(`InMemorySessionStore`, `InMemoryTaskStore`, `InMemoryResearchStateStore`,
`InMemoryArtifactStore`) satisfy them for tests.

---

## Configuration model

`config.py` defines typed configuration dataclasses (`SystemConfig`,
`ReasoningConfig`, `RuntimeConfig`, `SecurityConfig`, `PathsConfig`, `Config`).
Environment/file loading is deferred.

---

## Dependency direction (enforced)

```text
common ← domain ← research/tools/workflows/inference/persistence
```

Verified by construction and by the test suite: no MCP/Qwen/HTTP/database
imports exist below the adapter boundary.
