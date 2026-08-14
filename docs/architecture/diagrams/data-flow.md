# Data Flow

```mermaid
sequenceDiagram
    autonumber
    participant QS as Qwen Studio
    participant MCP as MCP Entrypoint
    participant GW as Local Research Gateway
    participant RET as Retrieval
    participant INF as Inference Adapter
    participant CMP as Computation / Tools
    participant VER as Verification Engine
    participant MEM as Memory / Artifact Manager

    QS->>MCP: MCP tool call (e.g. run_research)
    MCP->>MCP: permission check + arg validation
    MCP->>GW: typed request

    GW->>GW: intent + complexity → ReasoningProfile
    GW->>GW: decompose → tasks[]

    GW->>RET: retrieve evidence
    RET-->>GW: evidence records (cited)

    GW->>INF: generate (InferencePolicy)
    INF-->>GW: model output (structured)

    opt workflow requires computation
        GW->>CMP: run_analysis / query
        CMP-->>GW: deterministic result (audited)
    end

    GW->>VER: verify claims / find contradictions
    VER-->>GW: verification outcome

    GW->>MEM: persist research state + artifact
    MEM-->>GW: artifact metadata (provenance)

    GW->>MCP: final response + artifact refs
    MCP-->>QS: typed tool result
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
