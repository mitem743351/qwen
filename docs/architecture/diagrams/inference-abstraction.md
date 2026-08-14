# Inference Abstraction

```mermaid
flowchart TD
    subgraph POLICY["Provider-neutral"]
        RP["ReasoningProfile<br/>(name, planning_depth, retrieval_depth,<br/>evidence_threshold, independent_attempts,<br/>critique_passes, verification_passes,<br/>context_budget, output_budget,<br/>continuation_policy, parallelism)"]
        IP["InferencePolicy<br/>(sampling intent, budgets,<br/>structured output, tool use, streaming)"]
    end

    subgraph SEAM["Inference Adapter (translation layer)"]
        MAP["Profile → Policy →<br/>provider-specific parameters"]
        CAP["capability_info()<br/>+ graceful degradation"]
    end

    subgraph PROVIDERS["InferenceProvider implementations"]
        Q1["QwenProvider"]
        Q2["QwenCompatProvider"]
        Q3["LocalQwenProvider (future)"]
        Q4["OtherProvider (future)"]
    end

    RP -->|"Reasoning Policy Engine"| IP
    IP --> MAP
    MAP --> CAP
    MAP --> Q1
    MAP --> Q2
    MAP --> Q3
    MAP --> Q4

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
        +generate(prompt, policy) result
        +stream(prompt, policy) iterator
        +structured_output(schema, prompt, policy) result
        +tool_call(tools, messages, policy) result
        +model_info() ModelInfo
        +capability_info() CapabilityInfo
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

`ReasoningProfile` (behavior) and `InferencePolicy` (how to call) are
provider-neutral. Only the adapter knows provider-specific parameter names, and
only the adapter consults `capability_info()` to degrade gracefully when a
backend cannot honor part of a policy.
