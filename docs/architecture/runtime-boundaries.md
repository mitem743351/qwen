# Runtime Boundaries

The definitive statement of the three runtime layers that replace the Phase 0
"monolithic gateway." This is the central architectural correction of
Phase 0.75.

---

## 1. The Central Decision

Replace the single "Gateway" with **three logically distinct runtime layers**:

```text
                 CLIENT / INTERFACE
                        │
              ┌─────────┴─────────┐
              │                   │
         Qwen Studio          Future CLI/API
              │                   │
              └─────────┬─────────┘
                        │
                        ▼
                 ┌─────────────┐
                 │ MCP SERVER  │
                 └──────┬──────┘
                        │
                        ▼
              ┌───────────────────┐
              │ RESEARCH RUNTIME  │
              │ orchestration     │
              │ reasoning policy  │
              │ retrieval         │
              │ memory            │
              │ verification      │
              │ workflows         │
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │ INFERENCE RUNTIME │
              │ provider routing  │
              │ Qwen API          │
              │ local Qwen        │
              │ other providers   │
              └───────────────────┘
```

These are **logical boundaries first**, not deployment units. For a
single-machine installation they are initially implemented as **libraries and
in-process modules**, with local IPC only where justified and separate
processes only where isolation requires it. This phase does **not** mandate
three network daemons.

> **The statement this phase makes unambiguous:**
>
> **MCP is an external capability boundary. The Research Runtime is the
> provider-independent research and orchestration layer. The Inference Runtime
> is the provider-facing model execution layer. They are logically separate
> even when deployed in one local process.**

---

## 2. MCP Server

The MCP Server is the **capability exposure boundary** — not the entire
research system, and not an inference controller.

**Owns:**

```text
MCP Server
├── protocol handling
├── tool registry (the MCP-facing view)
├── resource exposure
├── request validation
├── permission enforcement
├── authentication where applicable
├── session/tool correlation
├── transport
└── translation between MCP schemas and runtime APIs
```

**Must NOT own:**

```text
research planning
reasoning policy
deep retrieval algorithms
long-term memory logic
provider-specific inference orchestration
business workflows
```

Those belong to the Research Runtime. The MCP Server is an **adapter** between
the external protocol and the Research Runtime API — nothing more.

---

## 3. Research Runtime

The **core application layer** and the "operational brain" of the system.

**Owns:**

```text
Research Runtime
├── task classification
├── task decomposition
├── reasoning profiles
├── reasoning budgets
├── orchestration
├── workflows
├── context assembly
├── retrieval
├── memory
├── evidence management
├── verification
├── artifact management
├── computation coordination
├── state persistence
└── optional delegation to Inference Runtime
```

**Must be usable without MCP.** A future CLI, API, dashboard, scheduled
workflow, or another client must be able to invoke the same research
capabilities without pretending to be an MCP client. Its application API is
conceptual only for now:

```text
ResearchRuntime
    execute_task()
    continue_task()
    inspect_task()
    retrieve_context()
    verify_claim()
    run_workflow()
    get_state()
    save_artifact()
```

---

## 4. Inference Runtime

Owns **actual model invocation** in any mode where the system controls
inference (`GATEWAY_INFERENCE`, escalated `HYBRID`).

**Owns:**

```text
Inference Runtime
├── provider selection
├── model selection
├── provider capability discovery
├── inference-policy translation
├── parameter validation
├── request construction
├── streaming
├── structured output
├── tool-call handling where provider-owned
├── retries
├── provider errors
└── model response normalization
```

**Must NOT own:**

```text
research memory
corpus indexing
document retrieval
research workflow policy
claim verification
artifact provenance
```

Those live in the Research Runtime. The Inference Runtime never reaches upward.

---

## 5. Dependency Direction

```text
Interface
    ↓
MCP Server
    ↓
Research Runtime
    ↓
Inference Runtime
    ↓
Inference Provider
```

The Research Runtime additionally depends **laterally** on Retrieval, Memory,
Documents, Verification, Computation, Artifacts, and Persistence subsystems.
The Inference Runtime **never calls upward** into the Research Runtime. There
are no circular dependencies.

---

## 6. Control Boundaries

| Layer | Controls |
|-------|----------|
| **MCP Server** | what external clients can invoke; which tools/resources are exposed; which permissions are allowed |
| **Research Runtime** | what the task is; how it is decomposed; which workflow runs; what evidence is required; how much verification; what persistent state is relevant |
| **Inference Runtime** | how an inference backend is invoked; which provider/model; which supported parameters are sent; how responses are normalized |
| **Model Provider** | actual model behavior; actual hidden reasoning implementation; actual context/generation constraints |

These are never blurred.

---

## 7. Relationship to Control Planes (Phase 0.5)

The four-plane model maps onto the three runtimes:

```text
MCP Server                     → Interface Plane
Research Runtime               → Agent Plane + parts of Knowledge Plane
Inference Runtime              → Model Plane
Retrieval / Memory / Documents / Databases → Knowledge Plane
```

---

## 8. Reasoning Placement

```text
Reasoning Policy        → Research Runtime
Inference Parameters    → Inference Runtime
Actual model reasoning  → Model Provider
```

`XHIGH` therefore causes the Research Runtime to request more retrieval,
verification, trajectories, inference calls, context, and output — but only
gateway-owned inference can request provider-specific inference controls, and
only through the Inference Runtime.

---

## 9. Runtime Contracts

### MCP Server → Research Runtime

```text
MCPRequest
    tool
    arguments
    session_reference
    caller_identity
    permission_context
```

```text
MCPResult
    status
    result
    structured_data
    artifacts
    citations
    provenance
    state_updates
    errors
```

### Research Runtime → Inference Runtime

```text
InferenceRequest
    task_reference
    model_requirement
    inference_policy
    context
    tools
    response_format
    continuation_state
```

```text
InferenceResult
    status
    model
    content
    structured_output
    tool_calls
    usage
    provider_metadata
    warnings
    errors
```

Hidden chain-of-thought never appears in any of these.

---

## 10. Failure Isolation

| Failure | Effect | System behavior |
|---------|--------|-----------------|
| **MCP Server fails** | Qwen Studio loses external tools | Normal Studio conversation may continue |
| **Research Runtime fails** | MCP may stay reachable; research operations fail | Structured error; no partial fabrication |
| **Inference Runtime fails** | Research tools remain usable; gateway-owned reasoning cannot continue | Retry / provider switch / explicit failure per policy |
| **Retrieval fails** | No evidence available | Explicitly report insufficient evidence — never silently invent results |
| **Provider fails** | Model unavailable | Retry, switch providers, or return explicit failure |

Each is isolated so a failure in one runtime degrades a bounded capability, not
the whole system.

---

## 11. Decision Record

- [0018 — MCP Server vs Research Runtime separation](decisions/0018-mcp-vs-research-runtime.md)
- [0019 — Research Runtime vs Inference Runtime separation](decisions/0019-research-vs-inference-runtime.md)
- [0020 — Internal Tool Registry vs MCP exposure](decisions/0020-tool-registry-vs-mcp.md)
- [0021 — In-process vs IPC boundary policy](decisions/0021-in-process-vs-ipc.md)
- [0022 — Runtime failure isolation](decisions/0022-failure-isolation.md)

Diagrams: [`diagrams/runtime-architecture.md`](diagrams/runtime-architecture.md),
[`diagrams/failure-isolation.md`](diagrams/failure-isolation.md).
