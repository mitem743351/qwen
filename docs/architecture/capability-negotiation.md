# Capability Negotiation

How the system discovers what an inference backend can actually do, and how it
handles the gap between an abstract `InferencePolicy` and a real provider. The
governing rule: **capabilities are facts to be discovered, never assumptions.**

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
Capability negotiation      ← ProviderCapabilities
        ↓
Provider-specific parameters
```

The negotiation layer intersects the `InferencePolicy` with
`ProviderCapabilities` and assigns one of four outcomes to every policy
element:

| Policy | Meaning | Example |
|--------|---------|---------|
| **APPLY** | Provider supports it; pass the parameter through. | `max_output_tokens` honored |
| **DEGRADE** | Provider lacks it; apply the closest supported behavior and record the reduction. | native reasoning budget → emulate via more passes |
| **EMULATE** | Provider lacks it; reproduce the intent with supported primitives. | no structured output → prompt-constrained JSON + validation |
| **REJECT** | Cannot honor even approximately and it is required; fail the policy explicitly. | required tool-calling on a non-tool backend |

Every non-`APPLY` outcome is **recorded** in workflow state and audit log. The
system never silently drops an intent.

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
