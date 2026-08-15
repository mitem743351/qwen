# Execution Model

The exact execution paths for the three operating modes, expressed in terms of
the three runtime layers (MCP Server, Research Runtime, Inference Runtime).
There is **no** path in which Qwen Studio's model inference is routed through
the MCP Server.

---

## 1. STUDIO_NATIVE

```text
User
 ↓
Qwen Studio
 ↓
Qwen model
 ↓
Qwen chooses MCP tool
 ↓
MCP Server
 ↓
Research Runtime
 ↓
Retrieval / Memory / Computation / Verification
 ↓
result
 ↓
MCP Server
 ↓
Qwen Studio
 ↓
Qwen continues its own inference
```

- The **Inference Runtime is not on the request path** for the Studio model.
- The Research Runtime provides capabilities; it does **not** become the owner
  of the Studio model's reasoning loop.
- The only model-plane network traffic is Qwen Studio's own.
- **Implemented in Phases 2–7:** this path is live via the MCP server (stdio),
  exposing `create_session` / `execute_task` / `continue_task` /
  `get_task_state` / `get_session` / `get_research_state`, plus
  `search_corpus` (lexical/semantic/hybrid) and `get_source` over an indexed
  local corpus, the Phase 4 memory tools over persistent structured memory, the
  Phase 5 evidence-integrity tools, the Phase 6 computation tools, and the
  Phase 7 orchestration tools (`plan_research` / `start_research` /
  `get_research_status` / `pause_research` / `resume_research` /
  `cancel_research` / `get_research_summary`) over the deterministic workflow
  engine (see [`mcp-implementation.md`](mcp-implementation.md)). The workflow
  engine orchestrates capabilities but never invokes a model; the synthesis step
  is a provider-neutral `SynthesisRequest` boundary.

---

## 2. GATEWAY_INFERENCE

```text
User / Client
 ↓
MCP Server or direct Research Runtime API
 ↓
Research Runtime
 ↓
Task / Workflow
 ↓
Context + Retrieval + Memory
 ↓
Inference Runtime
 ↓
Qwen API / Local Qwen / Provider
 ↓
Model response
 ↓
Research Runtime
 ↓
Verification / tools / further inference
 ↓
Synthesis
 ↓
Client
```

- The Research Runtime may perform **iterative** model calls.
- The Inference Runtime is responsible for **each individual** model
  invocation.
- MCP is **one possible entry mechanism**, not the only one — a CLI/API client
  calls the Research Runtime directly.

> **Phase 8 (implemented).** The single-invocation `GATEWAY_INFERENCE` flow is
> live: `SynthesisRequest → InferenceRequest → Inference Runtime → Qwen Provider
> → InferenceResult`. Iterative reasoning loops, hybrid escalation, and
> multi-model trajectories remain future phases.

---

## 3. HYBRID

Two coordinated paths:

```text
User
 ↓
Qwen Studio
 ├──────────────→ Studio-native inference
 │
 └── escalation → Research Runtime
                       │
                       ▼
                 Inference Runtime
                       │
                       ▼
                  Qwen backend
                       │
                       ▼
                 Research Runtime
                       │
                       ▼
                    result
                       │
                       ▼
                  Qwen Studio
```

- The Research Runtime owns the escalated workflow.
- Qwen Studio remains the interaction surface.
- The handoff uses the `EscalationRequest`/`EscalationResult` contract
  (Phase 0.5).

---

## 4. Dependency Direction in Execution

```text
Interface → MCP Server → Research Runtime → Inference Runtime → Inference Provider
```

Every mode respects this direction. In `STUDIO_NATIVE` the chain is truncated
after the Research Runtime (capabilities only); in `GATEWAY_INFERENCE`/`HYBRID`
the full chain to the provider is exercised.

---

## 5. What Never Happens

```text
- Qwen Studio's model inference is never routed through the MCP Server.
- The MCP Server never constructs provider-specific HTTP requests.
- The Workflow Engine never emits provider-specific parameters directly.
- The Inference Runtime never calls back into the Research Runtime.
- Hidden chain-of-thought never crosses any runtime boundary.
```

Diagrams: [`diagrams/runtime-architecture.md`](diagrams/runtime-architecture.md),
[`diagrams/operating-modes.md`](diagrams/operating-modes.md).
