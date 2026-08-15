# Capability Negotiation

How the system discovers what an inference backend can actually do, and how it
handles the gap between an abstract `InferencePolicy` and a real provider. The
governing rule: **capabilities are facts to be discovered, never assumptions.**

> ### Core boundary (Phase 1.2)
>
> **Provider capability ≠ Research Runtime capability.** A provider that lacks
> `supports_reasoning_budget` cannot be "given" a reasoning budget just because
> the Research Runtime can allocate more workflow passes. `EMULATE` means *"the
> requested intent can be approximated by an external workflow mechanism"* —
> it must **not** mean *"pretend the provider supports the requested native
> parameter."*

---

## 1. ProviderCapabilities

The provider advertises, through `InferenceProvider.capabilities()`, what it
actually supports:

```text
ProviderCapabilities
    supports_reasoning              # native "thinking"/reasoning mode
    supports_reasoning_budget       # controllable reasoning/thinking budget
    supports_max_output_tokens      # controllable generation length
    supports_temperature            # sampling temperature
    supports_top_p                  # nucleus sampling
    supports_preserved_thinking      # exposes/returns thinking content
    supports_tool_calling
    supports_structured_output
    supports_streaming
    supports_parallel_generation
    supports_context_caching
```

Each field is a capability **fact**. The reasoning engine does not guess; it
asks. A provider that cannot honor a field reports it as unsupported, and the
negotiation layer responds per policy (§3).

---

## 2. ReasoningBudget

Reasoning effort is a **resource-allocation** policy, not a prompt. Each
`ReasoningProfile` implies a `ReasoningBudget`:

```text
ReasoningBudget
    inference_budget       # total inference passes/tokens available
    retrieval_budget       # corpus queries / evidence items
    tool_budget            # tool call count/cost
    context_budget         # model context allocation
    verification_budget    # verification passes
    output_budget          # response/report length
    time_budget            # wall-clock ceiling
    parallelism_budget     # concurrent trajectories
```

`XHIGH` and `EXTREME` are **resource profiles** — larger allocations across
these dimensions — not merely "more prompt." The scheduler **may later**
allocate these dynamically; no adaptive scheduling is implemented in this
phase.

---

## 3. Negotiation Pipeline

```text
ReasoningProfile
        ↓
InferencePolicy
        ↓
Capability negotiation      ← ProviderCapabilities + ProviderLimits
        ↓
NegotiationResult
   ├── ProviderInferencePolicy      (what the backend actually receives)
   └── WorkflowEmulationPlan        (what the Research Runtime does externally)
```

The negotiation layer intersects the `InferencePolicy` with
`ProviderCapabilities` (and optional `ProviderLimits`) and assigns one of four
outcomes to **every requested** policy element, recorded as a typed
`NegotiationDecision` (`element`, `requested`, `supported`, `capability_class`,
`outcome`, `reason`, `effective_value`, `emulation_strategy`):

| Policy | Meaning | Example |
|--------|---------|---------|
| **APPLY** | Provider supports it; pass the parameter through. | `max_output_tokens` honored |
| **DEGRADE** | A weaker but semantically valid provider behavior satisfies the request. | `max_output_tokens=100000` vs provider max `32000` → `effective_value=32000` |
| **EMULATE** | Provider lacks it; the Research Runtime approximates the intent via an external workflow strategy. | reasoning effort, parallel research, structured output |
| **REJECT** | Cannot honor even approximately and it is required; fail the policy explicitly. | required tool-calling / preserved-thinking on a non-supporting backend |

Every non-`APPLY` outcome is **recorded**; a `REJECT` raises the typed
`InferenceError`. The system never silently drops an intent and never silently
continues past a rejected requirement.

### Capability classification

Each decision carries a provider-neutral `capability_class`:

| Class | Meaning | Outcome when unsupported |
|-------|---------|--------------------------|
| `NATIVE` | provider directly supports it | `APPLY` (or `DEGRADE` on numeric overage) |
| `WORKFLOW_EMULATABLE` | provider lacks it, but the Research Runtime can approximate the intent | `EMULATE` (with an `emulation_strategy`) |
| `NON_EMULATABLE` | provider lacks it and the system cannot safely approximate it | `REJECT` if required; `DEGRADE` to default if optional |

Emulated capabilities **never** appear in the `ProviderInferencePolicy` and
never fabricate an `effective_value`; they appear only in the
`WorkflowEmulationPlan` with an explicit `emulation_strategy`.

### Model selection is not a capability

`model_requirement` is the **single authoritative** model-selection intent and
is **not** negotiated here: a provider adapter later translates it into a
provider-specific model identifier (Phase 1.1). `InferenceRequest` carries no
independent model requirement.

---

## 4. Mode Interaction

- **STUDIO_NATIVE:** the Inference Runtime is not on the request path, so no
  inference negotiation occurs at all — the system only negotiates
  *tool/capability* availability (what MCP tools exist), never provider
  parameters.
- **GATEWAY_INFERENCE:** full negotiation applies on every call (Research
  Runtime → Inference Runtime → provider).
- **HYBRID:** negotiation applies only to escalated, Research-Runtime-owned
  tasks.

---

## 5. Failure Modes

| Risk | Mitigation |
|------|------------|
| Assume a param exists that doesn't | `ProviderCapabilities` is authoritative; default is "unsupported" |
| Silent drop of a policy intent | Every non-APPLY outcome is recorded |
| XHIGH silently degrades to weak | Degradation is surfaced in workflow state, not hidden |
| Emulation drifts from intent | Emulated policies carry an explicit "emulated" marker for verification |

---

## 6. Decision Record

- [0015 — Capability negotiation (APPLY/DEGRADE/EMULATE/REJECT)](decisions/0015-capability-negotiation.md)

Diagram: [`diagrams/inference-abstraction.md`](diagrams/inference-abstraction.md).

## Phase 8 — enforced before dispatch

The `InferenceRuntime` runs `negotiate()` before every invocation and re-seats
the request's policy to the negotiated `provider_policy`, so the Qwen adapter
receives only parameters it actually supports. Emulated capabilities never
appear as native parameters (see [`inference-runtime.md`](inference-runtime.md)).

Negotiation is fed **effective** capabilities and limits
(`provider.capabilities(model, thinking_mode=…)` / `provider.limits(model)`,
Phases 8.1–8.3), so a numeric reasoning/thinking budget is applied natively on
models that support it (e.g. Qwen3-era thinking models) and emulated via
workflow passes elsewhere. Inference mode is part of the resolution: structured
output is unavailable while thinking is on, so a request combining reasoning
and structured output negotiates structured output to `EMULATE` rather than
falsely claiming native support.
