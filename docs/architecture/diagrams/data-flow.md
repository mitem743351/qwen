# Data Flow

The request path is **mode-dependent**. The first sequence below is the
`GATEWAY_INFERENCE` path (the only path that exercises the Inference Adapter);
the second is `STUDIO_NATIVE`.

## GATEWAY_INFERENCE

```mermaid
sequenceDiagram
    autonumber
    participant QS as Client (Studio or other)
    participant GW as Local Research Gateway
    participant RET as Retrieval
    participant INF as Inference Adapter
    participant NEG as Capability negotiation
    participant CMP as Computation / Tools
    participant VER as Verification Engine
    participant MEM as Memory / Artifact Manager

    QS->>GW: task request
    GW->>GW: intent + complexity → ReasoningProfile + ReasoningBudget
    GW->>GW: decompose → tasks[]

    GW->>RET: retrieve evidence
    RET-->>GW: evidence records (cited)

    GW->>INF: generate (InferencePolicy)
    INF->>NEG: intersect with ProviderCapabilities
    NEG-->>INF: APPLY / DEGRADE / EMULATE / REJECT
    INF-->>GW: model output (structured)

    opt workflow requires computation
        GW->>CMP: run_analysis / query
        CMP-->>GW: deterministic result (audited)
    end

    GW->>VER: verify claims / find contradictions
    VER-->>GW: verification outcome

    GW->>MEM: persist research state + artifact
    MEM-->>GW: artifact metadata (provenance)

    GW-->>QS: final response + artifact refs
```

## STUDIO_NATIVE

```mermaid
sequenceDiagram
    autonumber
    participant QS as Qwen Studio (owns inference)
    participant QM as Qwen model
    participant MCP as MCP Entrypoint
    participant GW as Gateway capability handlers

    QS->>QM: user request (Qwen reasons)
    QM->>MCP: MCP tool call (e.g. retrieve_evidence)
    MCP->>MCP: permission check + arg validation
    MCP->>GW: typed capability request
    GW-->>MCP: structured result (evidence / verification / computation)
    MCP-->>QM: typed tool result
    QM->>QS: Qwen continues its own inference loop
```

**Persistence side-channel (not shown for clarity)**

- After each stage, the Workflow Engine writes a **stage checkpoint** to the
  Memory Manager, enabling resume from the last completed stage.
- Hidden chain-of-thought never appears in any message above; only structured
  outputs cross these arrows.

**Ingest flow (separate, one-way)**

```mermaid
flowchart LR
    F["Filesystem"] --> D["Discovery"] --> I["Identification"]
    I --> H["Hash (content address)"]
    I --> M["Metadata"] --> P["Parser adapter"] --> N["Normalize"]
    N --> C["Chunk"] --> X["Index (lexical · semantic · metadata)"]
    C --> R["Relationships"]
    H -.->|"RAW preserved untouched"| RAW["corpus RAW"]
```
