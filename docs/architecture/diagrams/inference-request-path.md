# Inference Request Path

```mermaid
sequenceDiagram
    autonumber
    participant WE as Workflow Engine (Research Runtime)
    participant IR as Inference Runtime
    participant NEG as Capability negotiation
    participant PROV as InferenceProvider
    participant MODEL as Model backend

    WE->>IR: InferenceRequest<br/>(task_reference · model_requirement · inference_policy · context · tools · response_format · continuation_state)
    IR->>IR: provider + model selection
    IR->>PROV: capabilities()
    PROV-->>IR: ProviderCapabilities
    IR->>NEG: intersect InferencePolicy × ProviderCapabilities
    NEG-->>IR: APPLY / DEGRADE / EMULATE / REJECT
    IR->>PROV: provider-specific request
    PROV->>MODEL: invoke
    MODEL-->>PROV: raw response
    PROV-->>IR: provider response
    IR->>IR: normalize + validate
    IR-->>WE: InferenceResult<br/>(status · model · content · structured_output · tool_calls · usage · provider_metadata · warnings · errors)
```

**Rules**

- The Workflow Engine never constructs provider-specific requests; it only
  emits an `InferenceRequest`.
- The Inference Runtime never calls back into the Research Runtime.
- Hidden chain-of-thought never appears in `InferenceResult`.
- In `STUDIO_NATIVE` this path is not exercised at all.
