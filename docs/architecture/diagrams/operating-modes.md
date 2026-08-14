# Operating Modes

Three distinct execution paths. There is **no** universal
"Qwen Studio → gateway → inference" path.

## STUDIO_NATIVE (tool augmentation)

```mermaid
flowchart TD
    U["User"] --> QS["Qwen Studio"]
    QS --> QM["Qwen Model"]
    QM -->|"Qwen decides to call MCP"| MC["MCP Client"]
    MC --> LG["Local Gateway"]
    subgraph CAP["Gateway capabilities"]
        R["Retrieval"]
        M["Memory"]
        C["Computation"]
        V["Verification"]
        A["Artifacts"]
    end
    LG --> R
    LG --> M
    LG --> C
    LG --> V
    LG --> A
    R --> RES["structured result"]
    RES --> QS
    QS -->|"Qwen continues its own inference loop"| U
```

**Ownership:** Qwen Studio owns conversation, model selection, inference, and
reasoning. The gateway only provides capabilities.

## GATEWAY_INFERENCE (orchestration-owned)

```mermaid
flowchart TD
    U["Client<br/>(Qwen Studio or other)"] --> LG["Local Gateway"]
    LG --> RE["Reasoning Engine"]
    RE --> IP["Inference Policy"]
    IP --> NEG["Capability negotiation"]
    NEG --> PROV["InferenceProvider"]
    PROV --> QB["Qwen backend / local model"]
    QB --> TOOLS["Tool execution / retrieval / verification"]
    TOOLS -->|"iterate"| RE
    RE --> SYN["Synthesis"]
    SYN --> RES["Final result"]
    RES --> U
```

**Ownership:** the gateway owns the workflow and explicitly invokes the
inference backend.

## HYBRID (escalation)

```mermaid
flowchart TD
    QS["Qwen Studio"]
    QS -->|"normal task"| QM["native Qwen"]
    QS -->|"escalation"| GW["Gateway"]
    GW --> RP["reasoning policy"]
    RP --> IP["inference provider"]
    IP --> QB["Qwen backend"]
```

## Escalation boundary

```mermaid
flowchart LR
    SN["Studio-native context"] -->|"EscalationRequest<br/>(task · profile · required_capabilities ·<br/>reason · context_ref · session_ref)"| GW["Gateway-owned workflow"]
    GW -->|"EscalationResult<br/>(status · result · artifacts · citations ·<br/>state_updates · provenance)"| SN
```

## Four control planes

```mermaid
flowchart LR
    subgraph MP["Model plane"]
        M1["model / reasoning / generation /<br/>context window / provider params"]
    end
    subgraph AP["Agent plane"]
        A1["planning / tool selection / workflow /<br/>iteration / parallelism / retry / continuation"]
    end
    subgraph KP["Knowledge plane"]
        K1["documents / retrieval / memory /<br/>claims / evidence / datasets"]
    end
    subgraph IP2["Interface plane"]
        I1["Qwen Studio / CLI / API /<br/>dashboard / future clients"]
    end
```

The gateway always operates the **agent** and **knowledge** planes; it operates
the **model** plane only in `GATEWAY_INFERENCE`/`HYBRID` modes; the **interface**
plane is the client, not owned by the gateway.
