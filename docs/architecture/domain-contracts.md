# Domain Contracts

The internal application model and API. These are **conceptual contracts**, not
database schemas or wire formats — no implementation yet.

---

## 1. API Contract vs Transport

The architecture distinguishes the **API contract** from the **transport**:

```text
API contract          — what operations and data shapes exist
transport             — how bytes move (MCP, HTTP, stdio,
                         in-process call, Rust FFI, future RPC)
```

The same Research Runtime API is callable over any transport without changing
business logic. MCP is one transport/adapter, never the domain model.

---

## 2. Domain Model vs MCP Schema

Internal structures must **not** mirror MCP wire schemas everywhere:

```text
MCP schema → adapter → domain object → Research Runtime
```

```text
Research Runtime result → domain object → adapter → MCP result
```

This prevents external protocol decisions from contaminating the internal
architecture. If MCP changes version, the domain model does not.

---

## 3. Domain Objects

```text
Task
Session
ResearchPlan
ResearchState
Evidence
Claim
Source
Artifact
Workflow
ReasoningProfile
ReasoningBudget
InferencePolicy
InferenceResult
VerificationResult
EscalationRequest
EscalationResult
```

Each is an internal contract (Python protocol/`dataclass`-style shape; Rust FFI
types where relevant). None is defined by MCP.

---

## 4. Research Runtime API (conceptual)

```text
ResearchRuntime
    execute_task()       # start a research task
    continue_task()      # resume/continue a task
    inspect_task()       # read task state
    retrieve_context()   # assemble evidence/context
    verify_claim()       # verification entry point
    run_workflow()       # drive a named workflow
    get_state()          # read research state
    save_artifact()      # persist an artifact with provenance
```

This is the **provider-independent** application surface. MCP, CLI, API, and
dashboard all adapt onto it.

---

## 5. Runtime Contracts

```text
MCPRequest / MCPResult                      (MCP Server ↔ Research Runtime)
InferenceRequest / InferenceResult          (Research Runtime ↔ Inference Runtime)
```

Defined in [`runtime-boundaries.md`](runtime-boundaries.md#9-runtime-contracts).

---

## 6. Internal Tool Abstraction

The Research Runtime does not assume every tool is MCP. Tools originate from
many sources:

```text
MCP · internal library · Rust module · Python module ·
database · local process · future remote service
```

```text
Tool
    name
    description
    schema
    permission
    execution_context
    capability
```

MCP is **one adapter** around the tool registry (see
[`runtime-boundaries.md`](runtime-boundaries.md) and
[`component-boundaries.md`](component-boundaries.md)).

---

## 7. Task State Machine

```text
CREATED → CLASSIFIED → PLANNED → RETRIEVING → REASONING
        → EXECUTING → VERIFYING → SYNTHESIZING → COMPLETED
```

Additional states:

```text
PAUSED · WAITING · FAILED · CANCELLED · NEEDS_INPUT
```

A task is **resumable** at any state boundary. Workflow state is never encoded
only in memory — the architecture assumes persistence will eventually exist.

---

## 8. Decision Record

- [0023 — Runtime API and domain contracts](decisions/0023-runtime-api-domain-contracts.md)

Diagram: [`diagrams/task-state-machine.md`](diagrams/task-state-machine.md).
