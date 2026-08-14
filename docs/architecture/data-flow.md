# Data Flow

How data moves through the system: the request path, the ingest path, the
persistence path, and state transitions. Every flow obeys the downward
dependency rule.

---

## 1. Request Path (research request)

```text
Qwen Studio ──MCP tool call──▶ MCP Entrypoint
    │ permission check + arg validation
    ▼
Task Router ──▶ intent + complexity
    ▼
Reasoning Policy Engine ──▶ ReasoningProfile
    ▼
Task Decomposer ──▶ tasks[]
    ▼
Workflow Engine ──▶ stage loop
    │        ┌──────────────────────────────────────────┐
    │        │  stage: retrieve  ──▶ Retrieval pipeline  │
    │        │  stage: reason    ──▶ Inference Adapter   │
    │        │  stage: compute   ──▶ Computation/Tools   │
    │        │  stage: verify    ──▶ Verification Engine │
    │        │  stage: persist   ──▶ Memory/Artifact Mgr │
    │        └──────────────────────────────────────────┘
    ▼
Context Engine (assemble final) ──▶ final response
    ▼
MCP Entrypoint ──▶ Qwen Studio
```

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
Workflow Engine ──▶ Tools subsystem
    │   request carries declared permission class
    ▼
Permission Boundary (read | analyze | write | execute | destructive)
    │   deny/confirm as required
    ▼
Tool implementation (Filesystem / Git / other MCP)
    ▼
Audit log (what ran, arguments, result hash, duration)
```

Every tool invocation is audited. `write` and `destructive` operations require
independent enablement and, where configured, confirmation.

---

## 6. Data Direction Rules

| Data | Direction | Notes |
|------|-----------|-------|
| User request | Studio → MCP → Gateway | Downward |
| Tool result | Tools → Gateway → (context) | Upward, typed |
| Model output | Inference → Workflow Engine | Never to storage raw except as structured state |
| Corpus content | RAW → INDEXED → STRUCTURED → DERIVED | One-way, immutable source |
| Retrieval results | Retrieval → Context Engine | Only via typed evidence records |
| Observability events | All layers → log/telemetry | Redacted of chain-of-thought |

See the diagram [`diagrams/data-flow.md`](diagrams/data-flow.md).
