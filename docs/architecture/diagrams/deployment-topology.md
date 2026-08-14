# Deployment Topology

```mermaid
flowchart LR
    subgraph HOST["Single local machine"]
        QS["Qwen Studio<br/>(UI + MCP client)"]
        MCP["MCP Entrypoint<br/>(localhost only)"]
        GW["Local Research Gateway<br/>(in-process subsystems)"]
        RUST["Rust modules via FFI<br/>(scanner · hasher · watcher ·<br/>fast search · sandbox · process)"]
        PY["Python subsystems<br/>(retrieval · documents · computation ·<br/>verification · memory · inference)"]
        SQLITE[("SQLite<br/>system-of-record")]
        DUCKDB[("DuckDB<br/>analytics")]
        CORPUS[("corpus/<br/>immutable RAW")]
        ART[("artifacts/ + data/")]
    end

    subgraph REMOTE["External (network)"]
        API["Qwen API / compatible endpoint"]
        WEB["Web search<br/>(native Qwen Studio)"]
    end

    subgraph OPTIONAL["Optional (future)"]
        DASH["TypeScript dashboard<br/>(read-only observability)"]
    end

    QS --> MCP
    QS --> WEB
    MCP --> GW
    GW --> PY
    GW --> RUST
    PY --> SQLITE
    PY --> DUCKDB
    PY --> CORPUS
    PY --> ART
    GW -.->|"GATEWAY_INFERENCE / HYBRID only"| API
    DASH -.->|read-only| GW
```

**Binding rules shown here**

- `QS → MCP → GW` run on `127.0.0.1` / Unix sockets (local-only by default).
- `GW ↔ RUST` is **FFI (PyO3)**, not a network call.
- `GW ↔ PY` is in-process (no serialization boundary).
- The `GW → API` edge (model backend) is **conditional on mode**; it exists
  only in `GATEWAY_INFERENCE`/`HYBRID`. In `STUDIO_NATIVE` the gateway has no
  outbound model traffic — Qwen Studio's own web search/model connection is the
  only model-plane network.
- The dashboard is optional and read-only; the core runs without it.

**Process count in v1**

Exactly one long-lived core process (gateway + entrypoint + subsystems), plus
Qwen Studio as the external client, and optional ephemeral sandbox subprocesses
for computation. No microservices.
