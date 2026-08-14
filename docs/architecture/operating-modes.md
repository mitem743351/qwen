# Operating Modes and Inference Ownership

This document defines **who owns the model inference loop** in each operating
mode. It is the authoritative correction to any implication that "MCP server ⇒
control over Qwen Studio's inference."

---

## 1. The Core Rule

> **MCP extends a model with capabilities; it does not inherently grant the MCP
> server control over the host client's model inference parameters or reasoning
> loop.**

Two distinctions follow directly:

```text
Tool Control        ≠   Inference Control
Workflow Influence  ≠   Direct Model-Inference Control
```

The system must **never claim a capability that the selected interface does not
actually expose**. "The MCP server controls Qwen's thinking budget" is an
unsupported claim unless Qwen Studio explicitly exposes that control.

---

## 2. CapabilityMode

A first-class conceptual object describing what an operating mode can and
cannot control:

```text
CapabilityMode
    name
    inference_owner        # who owns the inference loop: STUDIO | GATEWAY | MIXED
    tool_owner             # who supplies tools/capabilities: STUDIO | GATEWAY | BOTH
    native_web_search      # true | false | provider-dependent
    gateway_inference      # whether the Inference Runtime invokes a backend directly
    reasoning_control      # none | limited | full (and by whom)
    output_control         # none | limited | full
    context_control        # none | partial | full
    persistent_state       # whether structured research state is persisted
    escalation_allowed     # whether hybrid escalation is permitted
```

Initial values:

```text
STUDIO_NATIVE
GATEWAY_INFERENCE
HYBRID
```

---

## 3. STUDIO_NATIVE

**Inference owner: Qwen Studio.** The local system is a tool-augmentation
layer only.

Qwen Studio owns:

- user conversation
- model selection
- model inference
- native web search
- generation
- reasoning loop

The local system provides:

- MCP tools
- local corpus access
- retrieval
- memory
- computation
- verification
- artifacts
- project state

```text
User
  ↓
Qwen Studio
  ↓
Qwen model
  ↓
Qwen decides to call MCP
  ↓
MCP Server
  ↓
Research Runtime
  ↓
Tools / Retrieval / Computation / Memory
  ↓
result
  ↓
MCP Server
  ↓
Qwen Studio
  ↓
Qwen continues
```

The **Inference Runtime is not on the request path** for the Studio model, and
the Research Runtime does **not** become the owner of the Studio model's
reasoning loop.

In this mode the system may **influence** the model through tool outputs and
structured capabilities, but must **not claim direct control** over:

```text
thinking budget
temperature
top_p
max generation tokens
provider-specific inference parameters
internal reasoning loop
```

unless Qwen Studio explicitly exposes those controls. Each of the above is
therefore described as **client-dependent** or **provider-dependent**, never
"supported."

---

## 4. GATEWAY_INFERENCE

**Inference owner: the local system (Research Runtime + Inference Runtime).**
The Research Runtime owns the workflow; the Inference Runtime invokes the
backend through the `InferenceProvider`.

```text
User
  ↓
Qwen Studio or another client
  ↓
MCP Server or direct Research Runtime API
  ↓
Research Runtime
  ↓
Reasoning Engine
  ↓
Inference Policy
  ↓
Inference Runtime
  ↓
Qwen API / Local Qwen / Compatible Backend
  ↓
Tool execution / retrieval / verification
  ↓
Iterative model calls
  ↓
Final result
```

In this mode the local system may control, **to the extent the provider supports it**:

```text
model selection
reasoning configuration
thinking configuration
generation budget
context assembly
tool availability
number of inference passes
parallel trajectories
critique passes
verification passes
continuation
structured output
retry policy
```

The Inference Runtime must **never assume** a provider supports a parameter
merely because the abstract architecture defines it. `InferenceProvider`
exposes provider capabilities (see [`capability-negotiation.md`](capability-negotiation.md))
and rejects or degrades unsupported policies explicitly.

---

## 5. HYBRID

Normal interaction stays within Qwen Studio; selected tasks escalate to the
Research Runtime for gateway-owned inference.

```text
                     Qwen Studio
                          │
             ┌────────────┴────────────┐
             │                         │
         normal task              deep task
             │                         │
             ▼                         ▼
      native Qwen                Research Runtime
                                       │
                                 reasoning policy
                                       │
                                Inference Runtime
                                       │
                              Qwen API / local model
```

The architecture defines an explicit **escalation boundary** (§6) but does **not**
implement automatic escalation yet.

Escalation may be based on (architecture only, no logic yet):

- task complexity
- user-selected mode
- requested reasoning depth
- required output length
- need for iterative verification
- required computation
- required parallel research
- corpus size
- requested workflow
- provider capabilities

---

## 6. Hybrid Escalation Contract

An abstract request:

```text
EscalationRequest
    task
    requested_reasoning_profile
    requested_output_profile
    required_capabilities
    reason
    current_context_reference
    session_reference
```

An abstract result:

```text
EscalationResult
    status
    result
    artifacts
    citations
    state_updates
    provenance
```

This contract defines **session handoff, context transfer, and state
synchronization** between the Studio-native and Research-Runtime-owned paths.
It is an interface contract only; no protocol is implemented in this phase.

---

## 7. Capability Matrix

Wording legend: **Yes** (guaranteed) · **Optional** · **provider-dependent** ·
**client-dependent** · **not guaranteed** · **No** (unavailable).

| Capability | STUDIO_NATIVE | GATEWAY_INFERENCE | HYBRID |
|------------|---------------|-------------------|--------|
| Qwen Studio UI | Yes | Optional | Yes |
| Native Qwen Web Search | Yes | Depends on backend | Yes |
| Local MCP | Yes | Yes | Yes |
| Local corpus | Yes | Yes | Yes |
| Retrieval | Yes | Yes | Yes |
| Memory | Yes | Yes | Yes |
| Verification | Yes | Yes | Yes |
| Deterministic computation | Yes | Yes | Yes |
| Artifact generation + provenance | Yes | Yes | Yes |
| Direct inference configuration | client-dependent / limited | Yes (provider-dependent) | Inference-Runtime-controlled for escalated tasks |
| Model selection / routing | No / limited | Yes | Yes for escalated tasks |
| Hidden reasoning-budget control | not guaranteed (client-dependent) | provider-dependent | provider-dependent (escalated) |
| Iterative multi-pass reasoning | tool/workflow assisted | Yes | Yes for escalated tasks |
| Long-output continuation | client-dependent | Research-Runtime-controlled | Research-Runtime-controlled for escalated tasks |
| Qwen API | Not necessarily | Yes | Yes |
| Local Qwen model | Not through Studio inference | Yes | Yes for escalated tasks |
| Parallel trajectories | No (client-dependent) | Yes | Yes for escalated tasks |
| Structured research state persistence | Yes | Yes | Yes |

**Never claim** (regardless of mode):

- MCP controls Studio's hidden thinking budget
- MCP raises model max-token limits
- MCP sets temperature/top_p on the Studio host model
- the local system "controls Qwen" in STUDIO_NATIVE mode

---

## 8. Mode Selection

Mode is an explicit **configuration/runtime choice**, not something inferred
silently:

- `STUDIO_NATIVE` — default; the local system is a pure MCP capability layer
  (MCP Server + Research Runtime; no Inference Runtime on the path).
- `GATEWAY_INFERENCE` — an explicit runtime (CLI/API/worker) where the Research
  Runtime owns the workflow and the Inference Runtime invokes a configured
  `InferenceProvider`.
- `HYBRID` — both are available, with an explicit escalation contract.

A given client/session binds to a mode; capability claims must match the bound
mode.

---

## 9. Security Boundary

Inference ownership is a **separate** security boundary from MCP permissions:

- Access to MCP tools does **not** grant permission to invoke arbitrary model
  backends.
- `STUDIO_NATIVE` must **not** implicitly gain access to Inference-Runtime-owned
  API credentials.
- Credentials remain isolated from tool payloads and model-visible context.

See [`security.md`](security.md) §"Inference ownership as a boundary".

---

## 10. Decision Record

- [0014 — Inference ownership and operating modes](decisions/0014-inference-ownership-modes.md)
- [0017 — Hybrid escalation contract](decisions/0017-hybrid-escalation.md)

Diagrams: [`diagrams/operating-modes.md`](diagrams/operating-modes.md).
