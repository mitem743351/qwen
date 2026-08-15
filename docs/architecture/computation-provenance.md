# Computation Provenance & Freshness

Every computation result is traceable to its inputs, operation, parameters,
and execution context. This makes results reproducible and lets verification
detect staleness.

---

## What is recorded

| Field | Source |
|-------|--------|
| input datasets | dataset id + content hash + resolved path |
| query / code | normalized SQL query hash, or Python source hash (SHA-256) |
| parameters | the operation parameters |
| execution profile | `SAFE`/`ANALYTICAL`/`NUMERICAL`/`SIMULATION` |
| seed | for deterministic/simulated operations |
| software versions | Python + DuckDB versions (runtime metadata) |
| result artifact | artifact reference(s) |

`code_hash` (`computation/hashes.py`) hashes Python source verbatim;
`query_hash` hashes a whitespace-normalized SQL query. Provenance never relies
on filenames.

---

## Dataset freshness

A computation's result records the **content hash** of each input dataset.
`ComputationService.computation_is_stale(computation_id)` re-resolves the
request's dataset references and compares current hashes against the recorded
ones — a changed dataset makes the computation stale. Stale results are never
silently reused.

---

## Computation results as evidence

A `ComputationResult` can become an `EvidenceRecord` (via provenance: dataset,
query/code, parameters, execution, artifact). But a successful computation
establishes only:

> "Given these inputs and this operation, the result was X."

It does **not** establish "the underlying hypothesis is true", and a resulting
claim is never auto-marked supported merely because a computation succeeded.

---

## Verification integration

Verification can detect: missing computation provenance, a failed computation,
a stale input dataset, a mismatched query/code hash, or a missing artifact.
Automatic numerical correctness proving is **not** in Phase 6 (a later
analytical-verification phase).
