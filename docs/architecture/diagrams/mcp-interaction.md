# MCP Interaction

```mermaid
sequenceDiagram
    autonumber
    participant QS as Qwen Studio (MCP client)
    participant EP as MCP Entrypoint
    participant REG as Tool Registry
    participant PB as Permission Boundary
    participant GW as Gateway handler
    participant AUD as Audit Log

    QS->>EP: tool request (name + args)
    EP->>REG: resolve tool + JSON Schema
    alt tool unknown or args invalid
        EP-->>QS: structured validation error
    else valid
        EP->>PB: check permission class<br/>(read | analyze | write | execute | destructive)
        alt not permitted (e.g. write/destructive disabled)
            EP-->>QS: structured denial (no silent downgrade)
            EP->>AUD: record denial
        else permitted
            EP->>GW: dispatch typed request
            GW-->>EP: typed result
            EP->>AUD: record call (args-hash, result-hash, latency)
            EP-->>QS: typed tool result
        end
    end
```

**Permission escalation model**

```mermaid
flowchart LR
    R["read"] --> A["analyze"] --> W["write"] --> E["execute"] --> D["destructive"]
```

Each arrow means "implies the previous capability but is controlled
independently." `write` and `destructive` are separately enabled and default
off; `destructive` additionally requires confirmation.

**Semantic tool surface (the only verbs exposed)**

```mermaid
flowchart LR
    subgraph READ
        S1["search_corpus"]
        S2["retrieve_evidence"]
        S3["read_source"]
        S4["get_research_state"]
        S5["get_project_context"]
    end
    subgraph ANALYZE
        S6["query_database"]
        S7["run_analysis"]
        S8["verify_claim"]
        S9["find_contradictions"]
    end
    subgraph WRITE
        S10["save_artifact"]
    end
```
