# Data Flow

The request path is **mode-dependent**. The first sequence below is the
`GATEWAY_INFERENCE` path (the only path that exercises the Inference Runtime);
the second is `STUDIO_NATIVE`.

## GATEWAY_INFERENCE

```mermaid
sequenceDiagram
    autonumber
    participant QS as Client (Studio or other)
    participant RR as Research Runtime
    participant RET as Retrieval
    participant IR as Inference Runtime
    participant NEG as Capability negotiation
    participant CMP as Computation / Tools
    participant VER as Verification Engine
    participant MEM as Memory / Artifact Manager

    QS->>RR: task request (via MCP Server or direct API)
    RR->>RR: intent + complexity → ReasoningProfile + ReasoningBudget
    RR->>RR: decompose → tasks[]

    RR->>RET: retrieve evidence
    RET-->>RR: evidence records (cited)

    RR->>IR: InferenceRequest (InferencePolicy)
    IR->>NEG: intersect with ProviderCapabilities
    NEG-->>IR: APPLY / DEGRADE / EMULATE / REJECT
    IR-->>RR: InferenceResult (structured)

    opt workflow requires computation
        RR->>CMP: run_analysis / query
        CMP-->>RR: deterministic result (audited)
    end

    RR->>VER: verify claims / find contradictions
    VER-->>RR: verification outcome

    RR->>MEM: persist research state + artifact
    MEM-->>RR: artifact metadata (provenance)

    RR-->>QS: final response + artifact refs
```

## STUDIO_NATIVE

```mermaid
sequenceDiagram
    autonumber
    participant QS as Qwen Studio (owns inference)
    participant QM as Qwen model
    participant MCP as MCP Server
    participant RR as Research Runtime capability handlers

    QS->>QM: user request (Qwen reasons)
    QM->>MCP: MCP tool call (e.g. retrieve_evidence)
    MCP->>MCP: permission check + arg validation + schema adaptation
    MCP->>RR: domain request (MCPRequest)
    RR-->>MCP: structured result (evidence / verification / computation)
    MCP-->>QM: typed tool result (MCPResult)
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
