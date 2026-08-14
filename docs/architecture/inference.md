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
workflow engine depend only on the `InferenceProvider` protocol.

---

## 3. The Translation Layer

```text
ReasoningProfile ──▶ InferencePolicy ──▶ Capability negotiation ──▶ Provider-specific parameters
```

This is the load-bearing abstraction. Four explicit objects:

| Object | Meaning | Owned by |
|--------|---------|----------|
| **ReasoningProfile** | *What behavior* we want (critique passes, retrieval depth, budgets…) | Reasoning Policy Engine |
| **InferencePolicy** | *How to call* a model, provider-neutrally (sampling intent, budget, structured output, tool use, streaming) | Reasoning Policy Engine → Adapter |
| **ProviderCapabilities** | *What the backend can actually do* (advertised, not assumed) | Inference Adapter (queried from provider) |
| **Provider parameters** | *What to send* to a specific backend (temperature, top_p, max_tokens, specific reasoning flags) | Inference Adapter |

**Capability negotiation:** the adapter intersects the `InferencePolicy` with
`ProviderCapabilities` and assigns each element an explicit outcome:

```text
APPLY    — supported: pass the parameter through
DEGRADE  — unsupported: apply closest supported behavior, record the reduction
EMULATE  — unsupported: reproduce the intent with supported primitives
REJECT   — required but impossible: fail the policy explicitly
```

Every non-`APPLY` outcome is recorded in workflow state and the audit log;
no intent is silently dropped. This is what keeps `XHIGH` meaningful across
backends: the *workflow* behavior (more passes, more verification) is
provider-independent; only the low-level sampling hints are provider-specific —
and where even those are unavailable, the system says so instead of pretending.

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

Note: this decoupling applies to the gateway-owned path. In `STUDIO_NATIVE`
mode the first three rows are owned by Qwen Studio and the gateway only
provides the lower five.

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
