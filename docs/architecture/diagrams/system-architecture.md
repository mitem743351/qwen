# System Architecture

```mermaid
flowchart TB
    subgraph L1["L1 · Interface"]
        QS["Qwen Studio<br/>(conversation + native web search)"]
        OC["Future CLI / API / dashboard"]
    end

    subgraph L2["L2 · Capability Exposure"]
        MCP["MCP Server<br/>(protocol · tool registry · permissions · validation · audit)"]
    end

    subgraph L3["L3 · Research Runtime"]
        SM["Session Manager"]
        TR["Task Router"]
        RPE["Reasoning Policy Engine"]
        TD["Task Decomposer"]
        WE["Workflow Engine"]
        CE["Context Engine"]
        MM["Memory Manager"]
        VE["Verification Engine"]
        AM["Artifact Manager"]
        TREG["Internal Tool Registry"]
    end

    subgraph L3b["L3b · Inference Runtime"]
        IR["Inference Runtime<br/>(routing · capability discovery · policy translation · invocation)"]
    end

    subgraph L4["L4 · Knowledge / Computation / Tools"]
        RET["Retrieval<br/>(pipeline)"]
        DOC["Documents<br/>(pipeline)"]
        CMP["Computation<br/>(Python · DuckDB)"]
        TOL["Tools<br/>(Filesystem · Git · Rust · other)"]
    end

    subgraph L5["L5 · Local Data"]
        DB["Relational store<br/>(SQLite / PostgreSQL)"]
        DDB["DuckDB<br/>(analytical)"]
        IDX["Index<br/>(lexical · semantic · metadata)"]
        COR["Corpus<br/>(RAW / INDEXED / STRUCTURED / DERIVED)"]
        BLB["Blob store<br/>(artifacts · cache · sessions)"]
    end

    QS --> MCP
    OC --> MCP
    MCP --> WE
    WE --> RET
    WE --> DOC
    WE --> CMP
    WE --> TOL
    RET --> IDX
    RET --> DB
    DOC --> COR
    DOC --> IDX
    CMP --> DDB
    TOL --> COR
    TOL --> BLB
    MM --> DB
    AM --> BLB
    AM --> DB
    WE -.->|"GATEWAY_INFERENCE / HYBRID only"| IR
    IR -.->|"model call · provider-neutral"| QW["Model backend<br/>(Qwen / local / other)"]
```

**Notes**

- Dependencies point strictly downward (Interface → MCP Server → Research
  Runtime → Inference Runtime → Provider).
- This is the **capability topology**, not a universal execution path. The
  `Inference Runtime` and its edge to the model backend are **conditional on
  mode**: dormant in `STUDIO_NATIVE`, active in `GATEWAY_INFERENCE`/`HYBRID`.
  See [`operating-modes.md`](operating-modes.md) and
  [`runtime-boundaries.md`](../runtime-boundaries.md).
- The Inference Runtime is the *only* component that contacts a model backend,
  through the provider-neutral `InferenceProvider` interface.
- `QW` (model backend) is outside the system and swap-able. In `STUDIO_NATIVE`
  the model backend lives inside Qwen Studio — its inference is never routed
  through the MCP Server.
