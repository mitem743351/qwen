# Data Flow

How data moves through the system: the request path, the ingest path, the
persistence path, and state transitions. Every flow obeys the downward
dependency rule. **The request path is mode-dependent** — there is no single
universal "Qwen Studio → gateway → inference" path, and Qwen Studio's model
inference is never routed through the MCP Server.

---

## 1. Request Path (research request)

### 1.1 STUDIO_NATIVE (tool augmentation — the default)

```text
Qwen Studio ──▶ Qwen model ──▶ Qwen decides to call MCP
    │                                │
    │                                ▼
    │                         MCP Server
    │                            │ permission check + arg validation
    │                            ▼
    │                    Research Runtime capability handler
    │                    (retrieve / verify / compute / memory)
    │                            │
    │◀────────── typed result ───┘
    ▼
Qwen continues reasoning (its own inference loop)
```

The Research Runtime provides **capabilities**; the local system never touches
the model's inference loop, parameters, thinking budget, or generation limits.

### 1.2 GATEWAY_INFERENCE (orchestration-owned)

```text
Client (Studio or other) ──▶ MCP Server or direct Research Runtime API
    ▼
Research Runtime
    ▼
Task Router ──▶ intent + complexity
    ▼
Reasoning Policy Engine ──▶ ReasoningProfile (+ ReasoningBudget)
    ▼
Task Decomposer ──▶ tasks[]
    ▼
Workflow Engine ──▶ stage loop
    │        ┌──────────────────────────────────────────────┐
    │        │  stage: retrieve  ──▶ Retrieval pipeline       │
    │        │  stage: reason    ──▶ Inference Runtime        │
    │        │                       └─▶ capability negotiation
    │        │                           └─▶ InferenceProvider
    │        │  stage: compute   ──▶ Computation/Tools        │
    │        │  stage: verify    ──▶ Verification Engine      │
    │        │  stage: persist   ──▶ Memory/Artifact Mgr      │
    │        └──────────────────────────────────────────────┘
    ▼
Context Engine (assemble final) ──▶ final response ──▶ client
```

### 1.3 HYBRID (escalation)

Normal tasks follow §1.1. A deep task crosses the **escalation boundary** via
an `EscalationRequest`, then follows §1.2 and returns an `EscalationResult`.

Each stage produces a **typed stage result** that is (a) persisted as workflow
state and (b) available to subsequent stages. Nothing flows between stages as
raw chat text.

---

## 2. Ingest Path (corpus material)

```text
Filesystem ──discovery──▶ Identification ──▶ Hasher
    │ (content address)                     │
    ▼                                       ▼
Metadata Extraction ◀───────────────────────┘
    ▼
Parser (adapter) ──▶ Normalization ──▶ Chunking
    ▼
Indexing ──▶ Relationship Extraction
    ▼
(RAW preserved untouched)  INDEXED + STRUCTURED stored
```

**Invariant:** the RAW source is hashed at identification and never modified.
All downstream products (INDEXED, STRUCTURED, DERIVED) reference the RAW hash,
so any derived item can be traced to its immutable origin.

---

## 3. Persistence Path (research state)

```text
Workflow stage results ──▶ Memory Manager
    ├── Session Memory   (working state)
    ├── Project Memory   (project-scoped facts)
    ├── Research Memory  (cross-project findings)
    ├── Unresolved Questions
    └── Decision History
Artifact generation ──▶ Artifact Manager ──▶ blob + metadata row
Verification outcome ──▶ Memory Manager ──▶ evidence/claim/decision
```

Only **structured reasoning state** is persisted (hypotheses, claims, evidence
references, decisions, unresolved questions, tool results, verification
outcomes, workflow state). Hidden chain-of-thought is never written anywhere.

---

## 4. Session Lifecycle

```text
[ OPEN ] ──▶ [ ACTIVE ] ──▶ [ CHECKPOINTED ] ──▶ [ RESUMED ]
                                    │
                                    └──▶ [ CLOSED ] ──▶ [ ARCHIVED ]
```

- **OPEN** — Session Manager creates the session and binds it to a project.
- **ACTIVE** — workflow runs; each stage writes state.
- **CHECKPOINTED** — resumable snapshot (completed stages, open tasks, context
  compaction state).
- **RESUMED** — Context Engine restores continuation state; workflow resumes
  from the last completed stage.
- **CLOSED / ARCHIVED** — read-only; raw sources and artifacts remain.

A session may be resumed days later on a different model backend without losing
research state, because the persisted state is **provider-independent**.

---

## 5. Tool Call Path (permission boundary)

```text
Workflow Engine (Research Runtime) ──▶ Internal Tool Registry
    │   request carries declared permission class
    ▼
Permission Boundary (read | analyze | write | execute | destructive)
    │   deny/confirm as required
    ▼
Tool implementation (Filesystem / Git / Rust module / other)
    ▼
Audit log (what ran, arguments, result hash, duration)
```

Every tool invocation is audited. `write` and `destructive` operations require
independent enablement and, where configured, confirmation. MCP is one adapter
onto the Internal Tool Registry, not the registry itself.

---

## 6. Data Direction Rules

| Data | Direction | Notes |
|------|-----------|-------|
| User request | Studio → MCP Server → Research Runtime (STUDIO_NATIVE) or Client → Research Runtime (GATEWAY_INFERENCE) | Mode-dependent |
| Tool result | Tools → Research Runtime → (context) | Upward, typed |
| Model output | Inference Runtime → Research Runtime (Workflow Engine) | **GATEWAY_INFERENCE/HYBRID only**; never to storage raw except as structured state |
| Escalation handoff | Studio → Research Runtime (`EscalationRequest` → `EscalationResult`) | HYBRID only |
| Corpus content | RAW → INDEXED → STRUCTURED → DERIVED | One-way, immutable source |
| Retrieval results | Retrieval → Context Engine | Only via typed evidence records |
| Observability events | All layers → log/telemetry | Redacted of chain-of-thought |

See the diagram [`diagrams/data-flow.md`](diagrams/data-flow.md).
