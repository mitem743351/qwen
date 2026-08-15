# Inference Abstraction

Every model call goes through a provider-independent interface. The reasoning
engine never sees provider-specific parameters, and the system survives a
backend change. **Inference ownership is conditional on operating mode** (see
[`operating-modes.md`](operating-modes.md)): the abstraction is exercised only
in `GATEWAY_INFERENCE` and escalated `HYBRID` tasks.

---

## 1. The Interface

```text
InferenceProvider
    capabilities()         # ProviderCapabilities — what this backend can do
    model_info()           # identity, context window, cost
    generate()             # one-shot completion
    stream()               # streaming completion
    structured_output()    # constrained/typed output (JSON schema)
    tool_call()            # tool/function calling loop
```

All methods are **async-first** (where the runtime supports it) and return
typed results that include token usage when the provider reports it.

### 1.1 ProviderCapabilities (capabilities, not assumptions)

```text
ProviderCapabilities
    supports_reasoning
    supports_reasoning_budget
    supports_max_output_tokens
    supports_temperature
    supports_top_p
    supports_preserved_thinking
    supports_tool_calling
    supports_structured_output
    supports_streaming
    supports_parallel_generation
    supports_context_caching
```

The provider **advertises** these facts; the reasoning engine **never
assumes** a parameter exists merely because the abstract architecture defines
it. Unsupported parameters are handled by explicit negotiation policies (see
[`capability-negotiation.md`](capability-negotiation.md)).

---

## 2. Adapters

```text
QwenProvider            — official Qwen API
QwenCompatProvider      — any Qwen-compatible (OpenAI-style) endpoint
LocalQwenProvider       — future local Qwen model (e.g. vLLM/llama.cpp) — future
OtherProvider           — future alternative model providers — future
```

Adapter selection is **configuration**, not code. The reasoning engine and
workflow engine (in the Research Runtime) depend only on the `InferenceProvider`
protocol, mediated by the **Inference Runtime** — the provider-facing execution
layer that owns routing, capability discovery, policy translation, and response
normalization (see [`runtime-boundaries.md`](runtime-boundaries.md)).

---

## 3. The Translation Layer

```text
ReasoningProfile ──▶ InferencePolicy ──▶ Capability negotiation ──▶ Provider-specific parameters
```

This is the load-bearing abstraction. Four explicit objects:

| Object | Meaning | Owned by |
|--------|---------|----------|
| **ReasoningProfile** | *What behavior* we want (critique passes, retrieval depth, budgets…) | Reasoning Policy Engine (Research Runtime) |
| **InferencePolicy** | *How to call* a model, provider-neutrally (capability-aligned intents, see below) | Reasoning Policy Engine → Inference Runtime |
| **ProviderCapabilities** | *What the backend can actually do* (advertised, not assumed) | Inference Runtime (queried from provider) |
| **Provider parameters** | *What to send* to a specific backend (temperature, top_p, max_tokens, specific reasoning flags) | Inference Runtime |

`InferencePolicy` represents each intent as a capability-aligned,
provider-neutral field (Phase 1.1):

```text
model_requirement · reasoning · reasoning_budget · max_output_tokens
temperature · top_p · preserved_thinking · tool_calling · structured_output
streaming · parallel_generation · context_caching
```

`model_requirement` is the **single authoritative** model-selection intent and
is not a capability; `InferenceRequest` is a pure envelope that references the
policy and carries no independent model requirement.

**Capability negotiation:** the adapter intersects the `InferencePolicy` with
`ProviderCapabilities` (and optional `ProviderLimits`) and assigns **every**
requested capability an explicit outcome, recorded as a typed
`NegotiationDecision` (`requested`, `supported`, `capability_class`, `outcome`,
`reason`, `effective_value`, `emulation_strategy`):

```text
APPLY    — supported: pass the parameter through
DEGRADE  — a weaker but valid provider behavior satisfies the request
           (e.g. a numeric overage bounded to the provider limit)
EMULATE  — unsupported: approximate the intent via external workflow behavior
REJECT   — required but impossible: fail the policy explicitly
```

Each decision carries a provider-neutral `CapabilityClass`
(`NATIVE` / `WORKFLOW_EMULATABLE` / `NON_EMULATABLE`). The negotiated result is
a `NegotiationResult` that **separates**:

```text
ProviderInferencePolicy   — only what the backend will actually receive
                            (native + degraded values; emulated → absent)
WorkflowEmulationPlan     — external workflow directives for emulated intents
```

`EMULATE` is a workflow strategy, **not** a native inference parameter: an
emulated capability never appears in the provider policy and never fabricates
an `effective_value`. A `REJECT` raises a typed `InferenceError` — no intent is
silently dropped and nothing silently continues. This is what keeps `XHIGH`
meaningful across backends: the *workflow* behavior (more passes, more
verification) is provider-independent; only the low-level sampling hints are
provider-specific — and where even those are unavailable, the system says so
instead of pretending.

---

## 4. What Is Explicitly Decoupled

| Decoupled | Mechanism |
|-----------|-----------|
| Model capability | `capabilities()`; never hard-coded assumptions |
| Inference configuration | `InferencePolicy` |
| Reasoning workflow | Workflow Engine (independent of any provider) |
| Tool execution | Tools subsystem |
| Knowledge retrieval | Retrieval pipeline |
| Persistent state | Memory Manager |
| Verification | Verification Engine |
| Deterministic computation | Computation subsystem |

Note: this decoupling applies to the `GATEWAY_INFERENCE`/`HYBRID` path. In
`STUDIO_NATIVE` mode the first three rows are owned by Qwen Studio and the
local system (Research Runtime) only provides the lower five — the Inference
Runtime is not on the request path.

---

## 5. Failure Modes & Mitigations

| Risk | Mitigation |
|------|------------|
| Provider lock-in | Everything above `InferenceProvider` is provider-neutral |
| Backend param drift | Params live only inside adapters |
| Unsupported capability | `capabilities()` + explicit `APPLY`/`DEGRADE`/`EMULATE`/`REJECT` |
| Silent capability loss (XHIGH → weak) | Degradation is recorded and surfaced in workflow state |
| Assuming a param exists that doesn't | `ProviderCapabilities` is authoritative; default is "unsupported" |
| Claiming inference control in STUDIO_NATIVE | Mode selector blocks it; no inference adapter is exercised |
| Streaming vs one-shot mismatch | `stream()` optional; orchestrator uses `generate()` fallback |
| Token accounting absent | Usage captured when reported; otherwise budgeted by approximation |

---

## 6. Decision Record

- [0004 — Provider-independent inference abstraction](decisions/0004-inference-abstraction.md)
- [0003 — Reasoning profile as policy](decisions/0003-reasoning-profile-as-policy.md)
- [0015 — Capability negotiation (APPLY/DEGRADE/EMULATE/REJECT)](decisions/0015-capability-negotiation.md)

See [`diagrams/inference-abstraction.md`](diagrams/inference-abstraction.md).

## Phase 8 — implemented

The provider-neutral `InferenceRuntime` and the first production adapter
(`QwenProvider`) are implemented. See [`inference-runtime.md`](inference-runtime.md),
[`providers.md`](providers.md), and [`qwen-provider.md`](qwen-provider.md).

Phase 8.1 makes capability discovery **model-specific** (per-model context
windows, thinking mode, numeric `thinking_budget`), represents full tool
schemas, validates structured output against the requested JSON Schema, and
enforces a real stream-idle timeout.
