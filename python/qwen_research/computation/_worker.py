"""Sandbox worker subprocess for controlled Python execution.

This fixed, trusted script is invoked by :class:`PythonExecutor` as an OS
subprocess. It reads a JSON payload on stdin, executes the supplied source in
a restricted namespace (a whitelist of builtins + a small set of preloaded
stdlib modules — no ``__import__``, ``open``, ``eval``, ``exec``, ``socket``,
``subprocess``, or ``os``), and writes a JSON result to stdout.

This restricts the *straightforward* escape vectors (import, file open,
network, subprocess) and bounds time/output. It is **not** a hardened security
boundary against an adversary exploiting Python object introspection; see
``docs/architecture/python-sandbox.md``.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys

#: The narrow set of builtins exposed to sandboxed code. Deliberately excludes
#: ``__import__``, ``open``, ``eval``/``exec``/``compile``, ``input``,
#: ``globals``/``locals``/``vars``, ``type``/``object``, attribute reflection,
#: and exit hooks.
_SAFE_BUILTINS: dict[str, object] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "isinstance": isinstance,
    "repr": repr,
    "print": print,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "StopIteration": StopIteration,
    "None": None,
    "True": True,
    "False": False,
}

_MODULES: dict[str, object] = {
    "math": math,
    "random": random,
    "statistics": statistics,
    "json": json,
}


def _try_set_memory_limit(limit_bytes: int | None) -> None:
    if not limit_bytes:
        return
    try:
        import resource  # noqa: PLC0415 — POSIX-only, imported lazily

        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (ImportError, ValueError, OSError):  # platform-dependent; best effort
        pass


def main() -> None:
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    seed = payload.get("seed")
    memory_limit = payload.get("memory_limit")
    allowed = payload.get("allowed_modules", list(_MODULES))

    _try_set_memory_limit(memory_limit)

    namespace: dict[str, object] = {"__builtins__": _SAFE_BUILTINS}
    for name in allowed:
        if name in _MODULES:
            namespace[name] = _MODULES[name]

    if seed is not None:
        random.seed(seed)

    exec(compile(code, "<sandbox>", "exec"), namespace)  # noqa: S102 — bounded, subprocess

    result = namespace.get("RESULT")
    sys.stdout.write(json.dumps({"ok": True, "result": result}))


if __name__ == "__main__":
    try:
        main()
    except BaseException as exc:  # noqa: BLE001 — report any sandbox failure
        sys.stdout.write(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        )
