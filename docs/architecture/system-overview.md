# System Overview

This document gives the end-to-end picture: the five layers, what each owns,
and how a single research request travels through the system. It is the
orientation document for everything else.

---

## 1. The Five Layers

```text
┌──────────────────────────────────────────────────────────────┐
│  L1 · Qwen Studio                                            │
│      Human-facing conversation + native capabilities (search) │
└──────────────────────────────┬───────────────────────────────┘
                               │ MCP (model context protocol)
┌──────────────────────────────▼───────────────────────────────┐
│  L2 · MCP Entrypoint                                          │
│      Tool surface, permissions, protocol translation          │
└──────────────────────────────┬───────────────────────────────┘
                               │ typed tool requests
┌──────────────────────────────▼───────────────────────────────┐
│  L3 · Local Research Gateway (Reasoning + Orchestration)      │
│      Sessions, routing, policies, decomposition, workflows,   │
│      context, memory, verification, artifacts, inference      │
└───────────────┬───────────────┬───────────────┬──────────────┘
                │               │               │
     ┌──────────▼────┐  ┌───────▼───────┐  ┌────▼──────────────┐
     │ L4 · Retrieval│  │L4 · Documents │  │L4 · Computation   │
     │   (knowledge) │  │   (knowledge) │  │   & Tools         │
     └──────────┬────┘  └───────┬───────┘  └────┬──────────────┘
                │               │               │
┌───────────────▼───────────────▼───────────────▼──────────────┐
│  L5 · Local Data                                              │
│      Relational store · DuckDB · index · corpus · artifacts    │
└───────────────────────────────────────────────────────────────┘
```

Layer responsibilities, and what each layer is **not** allowed to do:

| Layer | Owns | Must not |
|-------|------|----------|
| **L1 Qwen Studio** | Conversation, rendering, native search, MCP client | Hold business logic; know about indexing or storage |
| **L2 MCP Entrypoint** | Tool registry, permission checks, JSON-RPC, arg validation | Contain reasoning or retrieval logic |
| **L3 Gateway** | Orchestration, policy, workflow, context, memory, verification, artifacts, inference | Talk to storage directly (except through managers); parse PDFs; run SQL |
| **L4 Capabilities** | Retrieval, document processing, computation, tools | Make workflow decisions; call the model directly |
| **L5 Local Data** | Durable state, index, corpus, blobs | Contain policy or business logic |

The contract between layers is **interfaces and schemas**, never shared mutable
state or cross-layer imports.

---

## 2. Key Entities at a Glance

- **Session** — one conversation/research episode; owns workflow runs.
- **Task** — a decomposed unit of work produced by the Task Decomposer.
- **Trajectory** — an independent reasoning path (future; interface only now).
- **Project** — long-lived scope binding sessions, corpus folders, memory.
- **Document / Source / Claim / Evidence / Entity** — the knowledge graph.
- **Decision / Question** — auditable reasoning state.
- **Artifact** — a first-class generated output with provenance.
- **ReasoningProfile / InferencePolicy** — how to reason vs. how to call the model.

---

## 3. The Central Inversion

The single most important design idea is an **inversion of control**:

> The model never drives the system. The **Workflow Engine drives the model.**

The model is invoked as one step inside a larger deterministic scaffold. The
scaffold decides: whether to retrieve, whether to decompose, when to critique,
when to verify, when to compute, and when to stop. This is what makes the
system reproducible, resumable, and auditable — and what lets `XHIGH` be a real
behavior instead of a long prompt.

This inversion also guarantees separation of the eight concerns (Section 2 of
`ARCHITECTURE.md`): the workflow engine orchestrates; the inference adapter
configures the model; the tools execute; the retrieval pipeline fetches
knowledge; the memory manager persists state; the verification engine checks
claims; the computation subsystem does deterministic math.

---

## 4. One Request, End to End (narrative)

1. User asks a question in **Qwen Studio**.
2. Qwen Studio sees an MCP server exposing semantic tools; it calls e.g.
   `retrieve_evidence` or a high-level `run_research` tool.
3. The **MCP Entrypoint** authenticates/authorizes the call against the tool's
   permission class (`read`/`analyze`/`write`/`execute`/`destructive`), validates
   arguments, and dispatches to the gateway.
4. The **Task Router** classifies intent and assesses complexity, which selects
   a **ReasoningProfile** via the **Reasoning Policy Engine**.
5. The **Task Decomposer** splits the request into tasks; the **Context Engine**
   plans what context is needed; the **Workflow Engine** begins executing stages.
6. The **Retrieval** subsystem (via Memory Manager + index) assembles evidence.
7. The **Inference Adapter** translates the profile into provider parameters and
   calls the model through an `InferenceProvider`.
8. Where the workflow calls for it, the **Computation** and **Tools**
   subsystems run deterministic work (Python/DuckDB/filesystem/Git).
9. The **Verification Engine** critiques claims, checks citations, and detects
   contradictions.
10. The **Artifact Manager** persists outputs with provenance; the **Memory
    Manager** persists research state.
11. The final response and any artifacts are returned through MCP to Qwen Studio.

See [`data-flow.md`](data-flow.md) for the formal flow.

---

## 5. Non-Goals (explicit)

For Phase 0 we explicitly do **not** commit to:

- A specific MCP SDK or vector database.
- A specific embedding model or reranker.
- The final directory layout being materialized now.
- Any network/distributed topology beyond "single local machine."

These are deferred decisions recorded in the ADRs and
[`architecture-review.md`](architecture-review.md), not open questions left to
drift.
