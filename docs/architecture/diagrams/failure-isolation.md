# Failure Isolation

```mermaid
flowchart TB
    subgraph MCPR["MCP Server"]
        M1["fails → Studio loses external tools;<br/>normal conversation continues"]
    end
    subgraph RR["Research Runtime"]
        R1["fails → MCP reachable;<br/>research operations fail with structured error"]
    end
    subgraph IRT["Inference Runtime"]
        I1["fails → research tools usable;<br/>gateway-owned reasoning cannot continue"]
    end
    subgraph RET["Retrieval"]
        F1["fails → report insufficient evidence;<br/>never invent results"]
    end
    subgraph PROV["Provider"]
        P1["fails → retry / switch provider /<br/>explicit failure per policy"]
    end

    MCPR --> RR --> IRT
    RR --> RET
    IRT --> PROV
```

Each runtime degrades a **bounded capability**, not the whole system (ADR 0022).

See [`runtime-boundaries.md`](../runtime-boundaries.md#10-failure-isolation) for
the full failure table.
