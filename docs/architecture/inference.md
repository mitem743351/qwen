# Inference Abstraction

Every model call goes through a provider-independent interface. The reasoning
engine never sees provider-specific parameters, and the system survives a
backend change.

---

## 1. The Interface

```text
InferenceProvider
    generate()             # one-shot completion
    stream()               # streaming completion
    structured_output()    # constrained/typed output (JSON schema)
    tool_call()            # tool/function calling loop
    model_info()           # identity, context window, cost
    capability_info()      # what this provider can actually control
```

All methods are **async-first** (where the runtime supports it) and return
typed results that include token usage when the provider reports it.

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
ReasoningProfile ──▶ InferencePolicy ──▶ Provider-specific parameters
```

This is the load-bearing abstraction. Three explicit objects:

| Object | Meaning | Owned by |
|--------|---------|----------|
| **ReasoningProfile** | *What behavior* we want (critique passes, retrieval depth, budgets…) | Reasoning Policy Engine |
| **InferencePolicy** | *How to call* a model, provider-neutrally (sampling intent, budget, structured output, tool use, streaming) | Reasoning Policy Engine → Adapter |
| **Provider parameters** | *What to send* to a specific backend (temperature, top_p, max_tokens, specific reasoning flags) | Inference Adapter |

**Capability-aware degradation:** the adapter consults `capability_info()`.
If a provider cannot honor part of an `InferencePolicy` (e.g. no
structured output, no reasoning toggle), the adapter:

1. applies the closest supported mapping,
2. records the degradation in the workflow state / audit log,
3. never silently drops the intent.

This is what keeps `XHIGH` meaningful across backends: the *workflow* behavior
(more passes, more verification) is provider-independent; only the low-level
sampling hints are provider-specific.

---

## 4. What Is Explicitly Decoupled

| Decoupled | Mechanism |
|-----------|-----------|
| Model capability | `capability_info()`; never hard-coded assumptions |
| Inference configuration | `InferencePolicy` |
| Reasoning workflow | Workflow Engine (independent of any provider) |
| Tool execution | Tools subsystem |
| Knowledge retrieval | Retrieval pipeline |
| Persistent state | Memory Manager |
| Verification | Verification Engine |
| Deterministic computation | Computation subsystem |

---

## 5. Failure Modes & Mitigations

| Risk | Mitigation |
|------|------------|
| Provider lock-in | Everything above `InferenceProvider` is provider-neutral |
| Backend param drift | Params live only inside adapters |
| Unsupported capability | `capability_info()` + graceful, logged degradation |
| Silent capability loss (XHIGH → weak) | Degradation is recorded and surfaced in workflow state |
| Streaming vs one-shot mismatch | `stream()` optional; orchestrator uses `generate()` fallback |
| Token accounting absent | Usage captured when reported; otherwise budgeted by approximation |

---

## 6. Decision Record

- [0004 — Provider-independent inference abstraction](decisions/0004-inference-abstraction.md)
- [0003 — Reasoning profile as policy](decisions/0003-reasoning-profile-as-policy.md)

See [`diagrams/inference-abstraction.md`](diagrams/inference-abstraction.md).
