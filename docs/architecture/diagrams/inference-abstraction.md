# Inference Abstraction

```mermaid
flowchart TD
    subgraph POLICY["Provider-neutral"]
        RP["ReasoningProfile<br/>(name, planning_depth, retrieval_depth,<br/>evidence_threshold, independent_attempts,<br/>critique_passes, verification_passes,<br/>context_budget, output_budget,<br/>continuation_policy, parallelism)"]
        RB["ReasoningBudget<br/>(inference · retrieval · tool · context ·<br/>verification · output · time · parallelism)"]
        IP["InferencePolicy<br/>(sampling intent, budgets,<br/>structured output, tool use, streaming)"]
    end

    subgraph SEAM["Capability Negotiation (translation layer)"]
        CAP["ProviderCapabilities<br/>(reasoning, reasoning_budget, max_output_tokens,<br/>temperature, top_p, preserved_thinking, tool_calling,<br/>structured_output, streaming, parallel, context_caching)"]
        NEG["outcome per policy element:<br/>APPLY · DEGRADE · EMULATE · REJECT"]
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
    NEG --> Q1
    NEG --> Q2
    NEG --> Q3
    NEG --> Q4

    Q1 -.-> B1["Qwen API"]
    Q2 -.-> B2["Qwen-compatible endpoint"]
    Q3 -.-> B3["local Qwen runtime"]
    Q4 -.-> B4["alternative provider"]
```

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
