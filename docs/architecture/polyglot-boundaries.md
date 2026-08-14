# Polyglot Boundaries

Where each language lives, why, and — most importantly — the **binding policy**
that prevents the polyglot architecture from becoming a distributed mess.

---

## 1. Language Ownership

### Python — the primary AI/reasoning language

Python owns everything that changes quickly, is model-adjacent, or is
experimental:

- reasoning orchestration and workflow logic
- agent logic and task decomposition
- retrieval orchestration and reranking
- document/PDF processing and metadata extraction
- embeddings
- verification
- inference adapters
- evaluation, data science, research workflows
- experimental algorithms

**Why Python:** ecosystem density (ML, NLP, document, scientific), rapid
iteration for reasoning logic, first-class support from model tooling, and the
fact that reasoning code is rarely the performance bottleneck.

### Rust — the systems/performance layer

Rust owns everything that must be fast, safe, or close to the OS:

- MCP infrastructure where justified (protocol framing, concurrency)
- high-performance filesystem scanning and indexing
- hashing
- file watching
- high-throughput search components
- concurrency and process management
- OS integration
- sandbox infrastructure
- performance-sensitive infrastructure

**Why Rust:** predictable performance, memory safety without GC pauses, strong
FFI story (PyO3), and safety guarantees that matter for sandboxing and file
access.

### TypeScript — optional UI infrastructure

Owns only the future dashboard/observability UI: monitoring dashboard, session
inspection, workflow visualization, corpus browser, artifact browser, system
controls, observability UI.

**Constraint:** TypeScript is **never** a runtime dependency of the core system.
The core must run fully without Node installed.

### SQL — a first-class implementation language

- **SQLite** — default, portable, single-file system-of-record.
- **PostgreSQL** — optional upgrade for larger persistent deployments.
- **DuckDB** — analytical workloads (Parquet/CSV, aggregations, joins, filtering).

**Constraint:** do not introduce all three in version one unless the
architecture requires it. Interfaces keep backends replaceable.

### Shell (Bash/PowerShell) — operations only

Installation, bootstrapping, diagnostics, service startup, backup, migration,
deployment. **No business logic in shell.**

---

## 2. Binding Policy

### 2.1 Python ↔ Rust

The default binding is **FFI via PyO3** (Rust compiled to a Python extension
module), not a network boundary. This gives:

- no serialization cost
- no network attack surface
- direct memory access where it matters
- Rust's safety around filesystem and process boundaries

**When FFI is justified** (i.e., Rust earns its place):

| Capability | Justification |
|------------|---------------|
| Filesystem scanning / indexing | Millions of files; GIL-free parallelism |
| Hashing (SHA-256 etc.) | Native speed, content-addressing of corpus |
| File watching | Low-latency, efficient OS APIs |
| High-throughput search (lexical, phrase) | Latency at scale |
| Sandbox / process management | Safety-critical, needs precise resource control |
| MCP protocol server core | Long-lived, concurrent connections |

**When Rust would be overengineering** (keep in Python):

- Workflow orchestration and reasoning logic (stateful, fast-changing)
- Anything in the document→index *metadata* path that is I/O-bound on parsing
  libraries (PDF/Office parsers live in Python anyway)
- Verification logic (experimental, model-adjacent)
- Inference adapters (network I/O bound; no CPU advantage)
- DuckDB/SQL orchestration (DuckDB is already a native engine)

The rule: **profile first, then choose Rust.** If the Python version is fast
enough for a single-user machine, Rust is not justified.

### 2.2 Python ↔ SQL

All SQL access goes through **repository interfaces** in Python. No raw SQL
strings appear in reasoning, workflow, or MCP code. DuckDB is used for
analytical reads, never as the authoritative store for memory/artifacts
(system-of-record is the relational store).

### 2.3 TypeScript ↔ core

TypeScript talks to the core **only** through a read-mostly observability
interface (structured logs, workflow state, metrics, artifact metadata). It
must never be required for core operation and never share a database connection
with the system-of-record except through read-only views.

---

## 3. Anti-patterns to Avoid

| Anti-pattern | Risk |
|--------------|------|
| Microservice per language | Network overhead, serialization tax, ops burden on a single machine |
| Rust reimplementation of PDF parsing | Duplication; Python libraries are superior here |
| Shell scripts doing reasoning | Unmaintainable, untestable business logic |
| Three databases in v1 | Operational complexity with no single-user payoff |
| Node required to run core | Breaks local-first portability |

---

## 4. Decision Record

See ADRs:

- [0002 — Polyglot boundaries](decisions/0002-polyglot-boundaries.md)
- [0011 — Local-first, in-process orchestration](decisions/0011-local-first-in-process.md)
