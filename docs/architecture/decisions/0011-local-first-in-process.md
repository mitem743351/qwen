# ADR 0011 — Local-first, in-process orchestration (no microservices)

- **Status:** Accepted

## Decision

Keep single-user local-first deployment fully supported: one gateway process
with in-process subsystems, local IPC/libraries/FFI over network calls between
components, and no microservices. TypeScript (dashboard) is optional and
non-essential. Defer any distributed topology until a measured need exists.

## Reason

The target deployment is a single local machine. Microservices would add
network boundaries, serialization, ops burden, and failure modes with no
scaling benefit. In-process modules keep latency low, deployment trivial, and
the architecture honest about its scale — while the manager interfaces leave a
path to later distribution if ever needed.

## Alternatives considered

- **Microservice zoo (gateway, worker, retrieval, compute as services):**
  explicitly rejected by the requirements.
- **Everything in one importable library with no process boundary at all:**
  acceptable; the "process" is a deployment detail, not an architectural
  commitment.

## Trade-offs

- Concurrency within one process must be managed (async + serialized mutations).
- Less isolation than processes (mitigated by sandboxing at the tool layer).

## Reversibility

Moderate-to-high. The gateway's internal components already talk through
interfaces; promoting one to a separate process is a contained change.
