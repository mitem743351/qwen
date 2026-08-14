# Credential / Security Boundaries

## Permission domains (layered)

```mermaid
flowchart LR
    CP["Client permissions"] --> MP["MCP permissions"] --> RP["Research Runtime permissions"] --> TP["Tool permissions"] --> IP["Inference provider permissions"]
```

A client allowed `search_corpus` is **not** automatically allowed `run_python`,
`invoke_inference_backend`, `write_files`, or `delete_files`.

## Credential boundary

```mermaid
flowchart TB
    subgraph NEVER["Never contains provider secrets"]
        A["MCP arguments"]
        B["tool output"]
        C["model-visible context"]
        D["research state"]
        E["logs"]
        F["artifacts"]
    end

    subgraph IRT["Inference Runtime (only home of secrets)"]
        S["provider adapter credentials"]
    end

    RR["Research Runtime<br/>requests 'invoke provider X'"] --> IRT
    IRT -.->|"secret never crosses back"| RR
```

- Provider secrets belong **exclusively** to the Inference Runtime / provider
  adapter.
- The Research Runtime may request *"invoke provider X"* but does not receive
  or manage the raw API key.
- A tool must not automatically gain access to provider credentials.

See [`security.md`](../security.md#38-permission-domains-layered) and
[`security.md`](../security.md#39-credential-boundary).
