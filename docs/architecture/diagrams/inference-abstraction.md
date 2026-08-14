# Inference Abstraction

```mermaid
flowchart TD
    subgraph POLICY["Provider-neutral"]
        RP["ReasoningProfile<br/>(name, planning_depth, retrieval_depth,<br/>evidence_threshold, independent_attempts,<br/>critique_passes, verification_passes,<br/>context_budget, output_budget,<br/>continuation_policy, parallelism)"]
        RB["ReasoningBudget<br/>(inference · retrieval · tool · context ·<br/>verification · output · time · parallelism)"]
        IP["InferencePolicy<br/>(sampling intent, budgets,<br/>structured output, tool use, streaming)"]
    end

    subgraph SEAM["Capability Negotiation (translation layer)"]
        CAP["ProviderCapabilities + ProviderLimits<br/>(reasoning, reasoning_budget, max_output_tokens,<br/>temperature, top_p, preserved_thinking, tool_calling,<br/>structured_output, streaming, parallel, context_caching)"]
        NEG["outcome per requested capability:<br/>APPLY · DEGRADE · EMULATE · REJECT<br/>+ CapabilityClass (NATIVE | WORKFLOW_EMULATABLE | NON_EMULATABLE)"]
    end

    subgraph RESULT["NegotiationResult"]
        PP["ProviderInferencePolicy<br/>(what the backend actually receives)"]
        WP["WorkflowEmulationPlan<br/>(what the Research Runtime does externally)"]
    end

    subgraph PROVIDERS["InferenceProvider implementations"]
        Q1["QwenProvider"]
        Q2["QwenCompatProvider"]
        Q3["LocalQwenProvider (future)"]
        Q4["OtherProvider (future)"]
    end

    RP --> RB
    RP -->|"Reasoning Policy Engine"| IP
    IP --> NEG
    CAP --> NEG
    NEG --> PP
    NEG --> WP
    PP --> Q1
    PP --> Q2
    PP --> Q3
    PP --> Q4

    Q1 -.-> B1["Qwen API"]
    Q2 -.-> B2["Qwen-compatible endpoint"]
    Q3 -.-> B3["local Qwen runtime"]
    Q4 -.-> B4["alternative provider"]
```

**Key property (Phase 1.2)**

`ReasoningProfile`/`ReasoningBudget` (behavior + resource allocation) and
`InferencePolicy` (how to call) are provider-neutral. Negotiation intersects
`InferencePolicy` with `ProviderCapabilities` (+ `ProviderLimits`) and produces
a `NegotiationResult` that **separates**:

- `ProviderInferencePolicy` — only what the backend will actually receive
  (native + degraded values). Emulated capabilities are **absent**.
- `WorkflowEmulationPlan` — the external workflow approximations for emulated
  capabilities (`EMULATE` ≠ pretending the provider supports a parameter).

This whole pipeline is exercised **only in `GATEWAY_INFERENCE`/`HYBRID` modes**;
in `STUDIO_NATIVE` it is not present in the execution path at all.

**Interface**

```mermaid
classDiagram
    class InferenceProvider {
        <<interface>>
        +capabilities() ProviderCapabilities
        +model_info() ModelInfo
        +generate(prompt, policy) result
        +stream(prompt, policy) iterator
        +structured_output(schema, prompt, policy) result
        +tool_call(tools, messages, policy) result
    }
    class QwenProvider {
        +__init__(config)
    }
    class QwenCompatProvider {
        +__init__(config)
    }
    class LocalQwenProvider {
        +__init__(config)
    }
    class OtherProvider {
        +__init__(config)
    }
    InferenceProvider <|.. QwenProvider
    InferenceProvider <|.. QwenCompatProvider
    InferenceProvider <|.. LocalQwenProvider
    InferenceProvider <|.. OtherProvider
```

**Key property**

`ReasoningProfile`/`ReasoningBudget` (behavior + resource allocation) and
`InferencePolicy` (how to call) are provider-neutral. The capability
negotiation layer intersects `InferencePolicy` with `ProviderCapabilities` and
assigns each element an explicit `APPLY`/`DEGRADE`/`EMULATE`/`REJECT` outcome —
never assuming a parameter exists. This whole pipeline is exercised **only in
`GATEWAY_INFERENCE`/`HYBRID` modes**; in `STUDIO_NATIVE` it is not present in
the execution path at all.
