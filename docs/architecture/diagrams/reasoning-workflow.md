# Reasoning Workflow

```mermaid
flowchart TD
    A["User Request"] --> B["Intent Classification"]
    B --> C["Complexity Assessment"]
    C --> D["Reasoning Profile Selection"]
    D --> E["Task Decomposition"]
    E --> F["Context Planning"]
    F --> G["Evidence Retrieval"]
    G --> H["Primary Reasoning"]
    H --> I["Tool / Computation Execution"]
    I --> J["Counterargument Generation"]
    J --> K["Critique"]
    K --> L["Verification"]
    L --> M{"Evidence threshold met?"}
    M -- no --> G
    M -- yes --> N["Synthesis"]
    N --> O["Citation / Provenance Audit"]
    O --> P["Final Response"]
    P --> Q["Persist Research State"]

    subgraph LEGEND["Stage skipping by profile"]
        S1["FAST: B → H → P"]
        S2["NORMAL: + G, K, L"]
        S3["DEEP: full path"]
        S4["XHIGH/EXTREME: full path + loop M→G, extra passes"]
    end
```

**Notes**

- `M → G` is the verification-driven loop: unmet evidence threshold sends the
  workflow back to retrieval, then reasoning.
- `K → L` (critique → verification) may itself repeat up to
  `critique_passes`/`verification_passes` from the active profile.
- Every stage checkpoints, so a resumed session restarts after the last
  completed stage (see `data-flow.md`).
