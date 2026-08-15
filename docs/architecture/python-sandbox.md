# Python Sandbox

Controlled Python execution for the `CUSTOM_PYTHON` operation (and the
`run_python` MCP tool, gated by the `EXECUTE` permission).

Module: `python/qwen_research/computation/sandbox.py` + `_worker.py`.

---

## Isolation model

Python executes in a **separate OS subprocess** (never inside the Research
Runtime process), communicating over a narrow structured protocol (JSON in →
JSON out). The worker:

- restricts `__builtins__` to a small whitelist (no `__import__`, `open`,
  `eval`/`exec`/`compile`, `input`, `globals`/`locals`/`vars`, `type`/`object`,
  attribute reflection, or exit hooks);
- preloads only `math`, `random`, `statistics`, `json`;
- applies the seed, if provided;
- enforces a time limit (subprocess timeout) and an output-size limit;
- applies a memory limit best-effort via `resource.setrlimit(RLIMIT_AS)`.

The default policy is: **no network, no arbitrary filesystem access, no
subprocess, no shell, no credentials, no environment secrets, no process
manipulation.** Only approved output locations are available (via the artifact
store, not the worker).

---

## Honest guarantees

This is a **restricted execution environment**, not a hardened security
boundary:

- It contains accidental/buggy model code and blocks the *straightforward*
  escape vectors (`import os`, `open("/etc/passwd")`, `import subprocess`,
  `import socket`, `eval`).
- It does **not** defend against a determined adversary exploiting Python
  object introspection (e.g. `().__class__.__bases__[0].__subclasses__()`).
  A builtins whitelist is not a security sandbox; seccomp/container isolation
  is future work.

Do not rely on `run_python` to execute adversarial code. It is `EXECUTE`-gated
and **disabled by default**; prefer `run_analysis` for structured operations.

---

## Enforced vs. best-effort limits

| Limit | Guarantee |
|-------|-----------|
| time limit | enforced (subprocess timeout) |
| output size | enforced (captured stdout capped) |
| memory | best-effort (POSIX `RLIMIT_AS`); not claimed as hard elsewhere |
| network / subprocess / filesystem / imports | blocked by builtins+namespace removal |

---

## Security tests

Negative tests assert that `import os`, `open`, `subprocess`, `socket`,
`eval`, `__import__`, and a timeout are all blocked/raised — behavior is
verified, not merely configuration.
