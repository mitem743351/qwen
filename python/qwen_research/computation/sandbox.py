"""Controlled Python execution in an OS subprocess.

:class:`PythonExecutor` runs model-supplied Python in a **separate OS process**
(never inside the Research Runtime) over a narrow structured protocol (JSON in
→ JSON out). It enforces a time limit and an output-size limit, and the worker
blocks the straightforward import/file/network/subprocess escapes. A memory
limit is applied best-effort via ``resource`` on POSIX platforms.

**Honesty:** this is a *restricted execution environment*, not a hardened
security boundary. It contains accidental/buggy code and blocks naive escapes,
but a determined adversary exploiting Python object introspection can defeat a
builtins whitelist. A true security sandbox (seccomp/container isolation) is
explicitly out of scope for Phase 6. Do not rely on this to execute adversarial
code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from qwen_research.domain.errors import (
    ExecutionTimeoutError,
    ResourceLimitError,
    SandboxError,
)

_WORKER = Path(__file__).with_name("_worker.py")


class PythonExecutor:
    """Execute restricted Python source in a subprocess."""

    def __init__(
        self,
        *,
        time_limit_seconds: float = 15.0,
        max_output_bytes: int = 256 * 1024,
        max_memory_bytes: int | None = None,
        allowed_modules: tuple[str, ...] = ("math", "random", "statistics", "json"),
    ) -> None:
        self._time_limit = time_limit_seconds
        self._max_output_bytes = max_output_bytes
        self._max_memory_bytes = max_memory_bytes
        self._allowed_modules = allowed_modules

    def execute(
        self,
        source: str,
        *,
        seed: int | None = None,
        variables: dict[str, object] | None = None,
        time_limit_seconds: float | None = None,
        max_output_bytes: int | None = None,
        max_memory_bytes: int | None = None,
    ) -> object:
        """Run *source* and return its ``RESULT`` binding.

        The supplied code must assign a serializable value to ``RESULT``. Any
        failure (timeout, output limit, sandbox error, or a Python exception in
        the worker) is reported as a typed :class:`ComputationError` subclass.
        Per-call limit overrides default to the executor's configured values.
        """
        time_limit = time_limit_seconds if time_limit_seconds is not None else self._time_limit
        output_limit = max_output_bytes if max_output_bytes is not None else self._max_output_bytes
        memory_limit = (
            max_memory_bytes if max_memory_bytes is not None else self._max_memory_bytes
        )
        payload = {
            "code": source,
            "seed": seed,
            "memory_limit": memory_limit,
            "allowed_modules": list(self._allowed_modules),
        }
        # Extra named variables are not supported (the sandbox has no import or
        # I/O); they are ignored rather than silently injected into scope.
        del variables
        try:
            proc = subprocess.run(
                [sys.executable, str(_WORKER)],
                input=json.dumps(payload),
                capture_output=True,
                timeout=time_limit,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionTimeoutError(f"python execution exceeded {time_limit}s") from exc

        if len(proc.stdout) > output_limit:
            raise ResourceLimitError(f"python output exceeded {output_limit} bytes")
        if proc.returncode != 0:
            raise SandboxError(f"python worker exited with code {proc.returncode}")

        try:
            decoded: Any = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SandboxError("python worker returned malformed output") from exc

        if not decoded.get("ok"):
            raise SandboxError(str(decoded.get("error", "sandbox execution failed")))
        return decoded.get("result")
