# System Architecture

```mermaid
flowchart TB
    subgraph L1["L1 · Interface"]
        QS["Qwen Studio<br/>(conversation + native web search)"]
    end

    subgraph L2["L2 · Protocol Boundary"]
        MCP["MCP Entrypoint<br/>(tool registry · permissions · validation · audit)"]
    end

    subgraph L3["L3 · Reasoning + Orchestration"]
        subgraph LRG["Local Research Gateway"]
            SM["Session Manager"]
            TR["Task Router"]
            RPE["Reasoning Policy Engine"]
            TD["Task Decomposer"]
            WE["Workflow Engine"]
            CE["Context Engine"]
            MM["Memory Manager"]
            VE["Verification Engine"]
            AM["Artifact Manager"]
            IA["Inference Adapter"]
        end
    end

    subgraph L4["L4 · Knowledge / Computation / Tools"]
        RET["Retrieval<br/>(pipeline)"]
        DOC["Documents<br/>(pipeline)"]
        CMP["Computation<br/>(Python · DuckDB)"]
        TOL["Tools<br/>(Filesystem · Git · other MCP)"]
    end

    subgraph L5["L5 · Local Data"]
        DB["Relational store<br/>(SQLite / PostgreSQL)"]
        DDB["DuckDB<br/>(analytical)"]
        IDX["Index<br/>(lexical · semantic · metadata)"]
        COR["Corpus<br/>(RAW / INDEXED / STRUCTURED / DERIVED)"]
        BLB["Blob store<br/>(artifacts · cache · sessions)"]
    end

    QS --> MCP
    MCP --> LRG
    LRG --> RET
    LRG --> DOC
    LRG --> CMP
    LRG --> TOL
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
    IA -.->|"model call · provider-neutral<br/>(GATEWAY_INFERENCE / HYBRID only)"| QW["Model backend<br/>(Qwen / local / other)"]
```

**Notes**

- Dependencies point strictly downward (L1→L5).
- This is the **capability topology**, not a universal execution path. The
  `Inference Adapter` and its edge to the model backend are **conditional on
  mode**: dormant in `STUDIO_NATIVE`, active in `GATEWAY_INFERENCE`/`HYBRID`.
  See [`operating-modes.md`](operating-modes.md) for the per-mode flows.
- The Inference Adapter is the *only* component that contacts a model backend,
  and it does so through the provider-neutral `InferenceProvider` interface.
- `QW` (model backend) is outside the system and swap-able. In `STUDIO_NATIVE`
  the model backend lives inside Qwen Studio, not behind the adapter.
