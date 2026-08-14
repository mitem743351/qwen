# Runtime Architecture

Three logically distinct runtimes replacing the monolithic "gateway".

```mermaid
flowchart TB
    subgraph IFACE["Interface"]
        QS["Qwen Studio"]
        OC["Future CLI / API / dashboard"]
    end

    subgraph MCPR["MCP Server (capability exposure)"]
        PROTO["protocol handling"]
        TREG["tool registry (MCP view)"]
        VAL["request validation"]
        PERM["permission enforcement"]
        ADAP["schema adapter (MCP ↔ domain)"]
    end

    subgraph RR["Research Runtime (provider-independent)"]
        TC["task classification / decomposition"]
        RP["reasoning profiles / budgets"]
        ORCH["orchestration / workflows"]
        CTX["context assembly"]
        RET["retrieval · memory · evidence"]
        VER["verification · artifacts"]
        STATE["state persistence"]
    end

    subgraph IRT["Inference Runtime (provider-facing)"]
        ROUTE["provider / model selection"]
        CAP["capability discovery"]
        TRANS["policy translation"]
        INV["invocation · streaming · retries"]
        NORM["response normalization"]
    end

    subgraph PROV["Model Provider"]
        Q1["Qwen API"]
        Q2["local Qwen"]
        Q3["other providers"]
    end

    QS --> MCPR
    OC --> MCPR
    MCPR --> RR
    RR --> IRT
    IRT --> PROV
```

## Dependency direction

```mermaid
flowchart LR
    IF["Interface"] --> MS["MCP Server"] --> RR2["Research Runtime"] --> IR2["Inference Runtime"] --> PR["Inference Provider"]
    RR2 --> SUBS["Retrieval · Memory · Documents · Verification · Computation · Artifacts · Persistence"]
```

- The Inference Runtime never calls upward into the Research Runtime.
- No circular dependencies.

## Logical vs deployed

```mermaid
flowchart LR
    subgraph ONE["One local process (v1)"]
        A["MCP Server module"]
        B["Research Runtime module"]
        C["Inference Runtime module"]
    end
    A --> B --> C
```

`apps/mcp-server`, `apps/research-runtime`, `apps/inference-runtime` are
logical runtimes — not three mandatory network daemons (ADR 0021).
