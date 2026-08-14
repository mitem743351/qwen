# Component Dependencies

```mermaid
flowchart TD
    QS["Qwen Studio"]
    MCP["MCP Entrypoint"]

    subgraph GW["Local Research Gateway"]
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

    subgraph RET["Retrieval"]
        QN["Query Normalizer"]
        CR["Candidate Retriever"]
        HR["Hybrid Ranker"]
        RR["Reranker"]
        EE["Evidence Extractor"]
        CIT["Citation Resolver"]
        CA["Context Assembler"]
    end

    subgraph DOC["Documents"]
        DISC["Discovery"]
        ID["Identification"]
        HASH["Hasher"]
        META["Metadata Extractor"]
        PARSE["Parser (adapters)"]
        NORM["Normalizer"]
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
        OM["Other MCP clients"]
    end

    subgraph STORE["Storage"]
        REPO["Repository interfaces"]
        SQLITE["SQLite / PostgreSQL"]
        DUCKDB["DuckDB"]
        VEC["VectorIndex"]
        BLOB["Blob store"]
    end

    QS --> MCP --> GW
    TR --> RPE
    TR --> TD
    WE --> CE
    WE --> MM
    WE --> VE
    WE --> AM
    WE --> IA
    WE --> RET
    WE --> CMP
    WE --> TOL
    CE --> MM
    VE --> RET
    VE --> MM
    MM --> REPO
    AM --> BLOB
    AM --> REPO

    RET --> QN --> CR --> HR --> RR --> EE --> CIT --> CA
    CR --> VEC
    CR --> SQLITE
    DOC --> DISC --> ID --> HASH --> META --> PARSE --> NORM --> CHUNK --> REL
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

- The gateway orchestrates; subsystems are leaves with respect to orchestration.
- `WE` (Workflow Engine) is the hub inside the gateway — it fans out to context,
  memory, verification, artifacts, inference, retrieval, computation, and tools.
- Subsystems never point back at the gateway or at each other.
- Storage is reached only through repository interfaces (`REPO`).
