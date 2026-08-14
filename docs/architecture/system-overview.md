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
| **L3 Gateway** | Orchestration, policy, workflow, context, memory, verification, artifacts, **inference (conditional on mode)** | Talk to storage directly (except through managers); parse PDFs; run SQL |
| **L4 Capabilities** | Retrieval, document processing, computation, tools | Make workflow decisions; call the model directly |
| **L5 Local Data** | Durable state, index, corpus, blobs | Contain policy or business logic |

The contract between layers is **interfaces and schemas**, never shared mutable
state or cross-layer imports.

> **The diagram above is the capability topology, not a universal execution
> path.** It shows what the gateway *can* provide. Whether the gateway actually
> drives the model depends on the operating mode (see
> [`operating-modes.md`](operating-modes.md)): in `STUDIO_NATIVE` the model and
> its inference loop live entirely inside Qwen Studio, and the gateway is only
> an MCP capability server. The **model plane** (the inference backend) is
> outside this stack and is only reachable by the gateway in
> `GATEWAY_INFERENCE`/`HYBRID` modes.

---

## 2. Key Entities at a Glance

- **Session** — one conversation/research episode; owns workflow runs.
- **Task** — a decomposed unit of work produced by the Task Decomposer.
- **Trajectory** — an independent reasoning path (future; interface only now).
- **Project** — long-lived scope binding sessions, corpus folders, memory.
- **Document / Source / Claim / Evidence / Entity** — the knowledge graph.
- **Decision / Question** — auditable reasoning state.
- **Artifact** — a first-class generated output with provenance.
- **ReasoningProfile / InferencePolicy / ReasoningBudget** — how to reason, how to call the model, and how much resource to allocate.
- **CapabilityMode** — the operating mode (`STUDIO_NATIVE` / `GATEWAY_INFERENCE` / `HYBRID`) that determines inference ownership.

---

## 3. The Central Inversion (mode-dependent)

The single most important design idea is an **inversion of control** — but it is
**conditional on inference ownership**:

> In `GATEWAY_INFERENCE` mode the model never drives the system; the **Workflow
> Engine drives the model.** In `STUDIO_NATIVE` mode the **model (Qwen Studio)
> drives the system**, and the workflow engine only *influences* it through tool
> outputs and structured capabilities.

In gateway-owned mode the model is invoked as one step inside a larger
deterministic scaffold. The scaffold decides: whether to retrieve, whether to
decompose, when to critique, when to verify, when to compute, and when to stop.
This is what makes the system reproducible, resumable, and auditable — and what
lets `XHIGH` be a real behavior instead of a long prompt.

In Studio-native mode the same scaffold exists but is *pulled by* the model:
the model chooses to call `retrieve_evidence`, `verify_claim`,
`find_contradictions`, etc., and the workflow engine shapes what those tools
return. That is **workflow influence**, not **direct model-inference control**.

This separation also guarantees the eight concerns (Section 2 of
`ARCHITECTURE.md`): the workflow engine orchestrates (agent plane); the
inference adapter configures the model only when the gateway owns inference
(model plane); the tools execute; the retrieval pipeline fetches knowledge
(knowledge plane); the memory manager persists state; the verification engine
checks claims; the computation subsystem does deterministic math.

---

## 4. End-to-End Narratives by Mode

There is **no single universal execution path**. The two primary paths are:

### 4.1 STUDIO_NATIVE (tool augmentation)

1. User asks a question in **Qwen Studio**; Qwen owns the conversation and the
   model inference loop.
2. Qwen Studio (its MCP client) decides to call a local tool, e.g.
   `retrieve_evidence` or `verify_claim`.
3. The **MCP Entrypoint** authorizes the call against the tool's permission
   class, validates arguments, and dispatches to the gateway.
4. The gateway runs the requested capability (retrieval, verification,
   computation, memory) and returns a **structured result**.
5. Qwen Studio continues reasoning with that result. The gateway never touches
   the model's parameters, thinking budget, or generation limits.

### 4.2 GATEWAY_INFERENCE (orchestration-owned)

1. A client (Qwen Studio *or* another client) submits a task to the gateway.
2. The **Task Router** classifies intent and complexity; the **Reasoning Policy
   Engine** selects a **ReasoningProfile** (and implied `ReasoningBudget`).
3. The **Task Decomposer** splits the task; the **Context Engine** plans
   context; the **Workflow Engine** begins executing stages.
4. The **Retrieval** subsystem assembles evidence.
5. The **Inference Adapter** translates the profile into an `InferencePolicy`,
   negotiates against `ProviderCapabilities`, and calls the model through an
   `InferenceProvider`.
6. **Computation/Tools** run deterministic work; **Verification** checks
   claims; the workflow may iterate (retrieve → reason → critique → verify).
7. The **Artifact Manager** persists outputs with provenance; the **Memory
   Manager** persists research state.
8. The final result is returned to the client.

### 4.3 HYBRID (escalation)

Normal tasks follow §4.1; deep tasks are handed to the gateway per the
[`EscalationRequest`/`EscalationResult`](operating-modes.md#6-hybrid-escalation-contract)
contract, then follow §4.2.

See [`data-flow.md`](data-flow.md) for the formal flow.

---

## 5. Non-Goals (explicit)

For Phase 0 we explicitly do **not** commit to:

- A specific MCP SDK or vector database.
- A specific embedding model or reranker.
- The final directory layout being materialized now.
- Any network/distributed topology beyond "single local machine."
- Automatic hybrid-escalation logic (only the contract is defined).

These are deferred decisions recorded in the ADRs and
[`architecture-review.md`](architecture-review.md), not open questions left to
drift.
