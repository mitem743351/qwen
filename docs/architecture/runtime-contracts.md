# Runtime Contracts

The application-layer contracts implemented in Phase 1: the Research Runtime,
the MCP application contracts, the internal Tool Registry, the Workflow
contracts, the Inference Provider protocol, and the persistence interfaces.

---

## Research Runtime

```text
ResearchRuntime (protocol, research/interfaces.py)
    execute_task()
    continue_task()
    inspect_task()
    retrieve_context()      # UnsupportedOperationError until Phase 3
    verify_claim()          # UnsupportedOperationError until Phase 6
    run_workflow()
    get_state()
    save_artifact()
    create_session()
```

`InMemoryResearchRuntime` (`research/runtime.py`) implements this over
in-memory stores. The API is transport-independent: MCP, CLI, API, and
dashboard will adapt onto the same surface.

- `execute_task` creates a task, classifies and plans it, and creates a
  `ResearchState`.
- `continue_task` advances one step along the active progression.
- `retrieve_context` / `verify_claim` raise `UnsupportedOperationError` (no
  fabricated results — B23).

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
