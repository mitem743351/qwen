# Internal Tool Registry

MCP is one adapter around the Internal Tool Registry, not the registry itself.

```mermaid
flowchart TB
    subgraph REG["Internal Tool Registry (neutral)"]
        T["Tool<br/>(name · description · schema · permission · execution_context · capability)"]
    end

    subgraph IMPL["Tool implementations"]
        FS["Filesystem Tool"]
        GIT["Git Tool"]
        PY["Rust module"]
        MOD["Python module"]
        DB["database"]
        PROC["local process"]
    end

    subgraph ADAP["Adapters"]
        MCPA["MCP adapter"]
        CLIA["CLI adapter"]
        APIA["API adapter"]
        WFA["Workflow adapter"]
    end

    REG --> IMPL
    MCPA --> REG
    CLIA --> REG
    APIA --> REG
    WFA --> REG
```

## MCP adapter boundary

```mermaid
flowchart LR
    QS["Qwen Studio (MCP client)"] --> MS["MCP Server"]
    MS -->|"MCP schema"| AD["Schema adapter"]
    AD -->|"domain object"| RR["Research Runtime"]
    RR -->|"domain object"| AD2["Schema adapter"]
    AD2 -->|"MCP result"| MS
```

- The MCP wire schema is **not** the internal domain model (ADR 0023).
- Only capabilities with a reason to be exposed are published as MCP tools;
  MCP is not the internal plugin architecture (ADR 0020).
