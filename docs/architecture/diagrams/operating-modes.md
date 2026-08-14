# Operating Modes

Three distinct execution paths. There is **no** universal
"Qwen Studio → gateway → inference" path, and Qwen Studio's model inference is
never routed through the MCP Server.

## STUDIO_NATIVE (tool augmentation)

```mermaid
flowchart TD
    U["User"] --> QS["Qwen Studio"]
    QS --> QM["Qwen Model"]
    QM -->|"Qwen decides to call MCP"| MC["MCP Client"]
    MC --> MS["MCP Server"]
    MS --> RR["Research Runtime"]
    subgraph CAP["Research Runtime capabilities"]
        R["Retrieval"]
        M["Memory"]
        C["Computation"]
        V["Verification"]
        A["Artifacts"]
    end
    RR --> R
    RR --> M
    RR --> C
    RR --> V
    RR --> A
    R --> RES["structured result"]
    RES --> MS --> QS
    QS -->|"Qwen continues its own inference loop"| U
```

**Ownership:** Qwen Studio owns conversation, model selection, inference, and
reasoning. The MCP Server + Research Runtime only provide capabilities; the
**Inference Runtime is not on the request path**.

## GATEWAY_INFERENCE (orchestration-owned)

```mermaid
flowchart TD
    U["Client<br/>(Qwen Studio or other)"] --> MS["MCP Server or direct Research Runtime API"]
    MS --> RR["Research Runtime"]
    RR --> RE["Reasoning Engine"]
    RE --> IP["Inference Policy"]
    IP --> IR["Inference Runtime"]
    IR --> NEG["Capability negotiation"]
    NEG --> PROV["InferenceProvider"]
    PROV --> QB["Qwen backend / local model"]
    QB --> TOOLS["Tool execution / retrieval / verification"]
    TOOLS -->|"iterate"| RE
    RE --> SYN["Synthesis"]
    SYN --> RES["Final result"]
    RES --> U
```

**Ownership:** the Research Runtime owns the workflow; the Inference Runtime
owns each individual model invocation.

## HYBRID (escalation)

```mermaid
flowchart TD
    QS["Qwen Studio"]
    QS -->|"normal task"| QM["native Qwen"]
    QS -->|"escalation"| RR["Research Runtime"]
    RR --> RP["reasoning policy"]
    RP --> IR["Inference Runtime"]
    IR --> QB["Qwen backend"]
    QB --> RR2["Research Runtime"]
    RR2 --> QS2["Qwen Studio (result)"]
```

## Escalation boundary

```mermaid
flowchart LR
    SN["Studio-native context"] -->|"EscalationRequest<br/>(task · profile · required_capabilities ·<br/>reason · context_ref · session_ref)"| RR["Research Runtime workflow"]
    RR -->|"EscalationResult<br/>(status · result · artifacts · citations ·<br/>state_updates · provenance)"| SN
```

## Four control planes → runtime ownership

```mermaid
flowchart LR
    subgraph MP["Model plane — Inference Runtime"]
        M1["model / reasoning / generation /<br/>context window / provider params"]
    end
    subgraph AP["Agent plane — Research Runtime"]
        A1["planning / tool selection / workflow /<br/>iteration / parallelism / retry / continuation"]
    end
    subgraph KP["Knowledge plane — Research Runtime + Retrieval/Memory/Documents"]
        K1["documents / retrieval / memory /<br/>claims / evidence / datasets"]
    end
    subgraph IP2["Interface plane — MCP Server (adapters)"]
        I1["Qwen Studio / CLI / API /<br/>dashboard / future clients"]
    end
```

The Research Runtime always operates the **agent** and (parts of the)
**knowledge** planes; the Inference Runtime operates the **model** plane only
in `GATEWAY_INFERENCE`/`HYBRID` modes; the **interface** plane is the client,
adapted by the MCP Server.
