# Component Dependencies

```mermaid
flowchart TD
    QS["Qwen Studio"]
    OC["Future CLI / API"]
    MCP["MCP Server"]

    subgraph RR["Research Runtime"]
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
        MS["Mode Selector (CapabilityMode)"]
    end

    subgraph IRT["Inference Runtime"]
        ROUTE["Provider Router"]
        DISC["Capability Discovery"]
        TRANS["Policy Translator (negotiation)"]
        INV["Invoker"]
        NORM["Response Normalizer"]
    end

    subgraph RET["Retrieval"]
        QN["Query Normalizer"]
        CR["Candidate Retriever"]
        HR["Hybrid Ranker"]
        RR2["Reranker"]
        EE["Evidence Extractor"]
        CIT["Citation Resolver"]
        CA["Context Assembler"]
    end

    subgraph DOC["Documents"]
        DISC2["Discovery"]
        ID["Identification"]
        HASH["Hasher"]
        META["Metadata Extractor"]
        PARSE["Parser (adapters)"]
        NORM2["Normalizer"]
        CHUNK["Chunker"]
        REL["Relationship Extractor"]
    end

    subgraph CMP["Computation"]
        PY["Python Sandbox Executor"]
        DDB["DuckDB Service"]
    end

    subgraph TOL["Tools"]
        FS["Filesystem Tool"]
        GIT["Git Tool"]
        OM["Other tool adapters"]
    end

    subgraph STORE["Storage"]
        REPO["Repository interfaces"]
        SQLITE["SQLite / PostgreSQL"]
        DUCKDB["DuckDB"]
        VEC["VectorIndex"]
        BLOB["Blob store"]
    end

    QS --> MCP
    OC --> MCP
    MCP --> WE
    MS --> WE
    TR --> RPE
    TR --> TD
    WE --> CE
    WE --> MM
    WE --> VE
    WE --> AM
    WE -.->|"gateway-owned modes only"| IRT
    WE --> RET
    WE --> CMP
    WE --> TOL
    CE --> MM
    VE --> RET
    VE --> MM
    MM --> REPO
    AM --> BLOB
    AM --> REPO

    IRT --> ROUTE --> DISC
    ROUTE --> TRANS --> INV --> NORM

    RET --> QN --> CR --> HR --> RR2 --> EE --> CIT --> CA
    CR --> VEC
    CR --> SQLITE
    DOC --> DISC2 --> ID --> HASH --> META --> PARSE --> NORM2 --> CHUNK --> REL
    CHUNK --> VEC
    CHUNK --> SQLITE
    CMP --> PY
    CMP --> DDB --> DUCKDB
    TOL --> FS
    TOL --> GIT
    TOL --> OM

    REPO --> SQLITE
    REPO --> DUCKDB
```

**Rules encoded here**

- The **Research Runtime** orchestrates; subsystems are leaves with respect to
  orchestration. The **MCP Server** is an adapter above it; the **Inference
  Runtime** is a leaf below it.
- `WE` (Workflow Engine) is the hub inside the Research Runtime — it fans out
  to context, memory, verification, artifacts, retrieval, computation, and
  tools.
- The `WE → Inference Runtime` edge is **dashed**: exercised only in
  `GATEWAY_INFERENCE`/`HYBRID` modes (enforced by the Mode Selector).
- The Inference Runtime never points back up into the Research Runtime.
- Subsystems never point back at the Research Runtime or at each other.
- Storage is reached only through repository interfaces (`REPO`).
