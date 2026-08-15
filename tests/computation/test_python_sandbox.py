"""Python sandbox tests (subprocess isolation + restricted builtins)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qwen_research.computation.sandbox import PythonExecutor
from qwen_research.domain.errors import ExecutionTimeoutError, SandboxError


def test_simple_arithmetic() -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    assert executor.execute("RESULT = 1 + 2 * 3") == 7


def test_preloaded_modules() -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    assert executor.execute("RESULT = math.sqrt(16) + statistics.mean([1, 2, 3])") == 6.0


def test_seeded_random() -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    a = executor.execute("RESULT = random.Random(42).random()", seed=42)
    b = executor.execute("RESULT = random.Random(42).random()", seed=42)
    assert a == b


@pytest.mark.parametrize(
    "code",
    [
        "import os\nRESULT = os.getcwd()",
        "RESULT = open('/etc/passwd').read()",
        "import subprocess\nRESULT = subprocess.run(['id'])",
        "import socket\nRESULT = socket.socket()",
        "RESULT = eval('1+1')",
        "RESULT = __import__('os').system('id')",
        "import sys\nRESULT = sys.argv",
    ],
)
def test_escape_vectors_blocked(code: str) -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    with pytest.raises(SandboxError):
        executor.execute(code)


def test_timeout_enforced() -> None:
    executor = PythonExecutor(time_limit_seconds=1)
    with pytest.raises(ExecutionTimeoutError):
        executor.execute("while True:\n    pass")


def test_result_requires_assignment() -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    # No RESULT binding → returns None (not an error).
    assert executor.execute("x = 5") is None


def test_exception_reported() -> None:
    executor = PythonExecutor(time_limit_seconds=10)
    with pytest.raises(SandboxError):
        executor.execute("RESULT = 1 / 0")


# -- documented limitation (honest, not a hardened boundary) ---------------
# The sandbox whitelists builtins, which blocks naive escapes, but Python
# object introspection can recover the *real* ``__builtins__`` dict and thus
# ``open``/``__import__``. These tests verify that limitation rather than
# pretending the sandbox is secure against a determined adversary.

_INTROSPECTION_ESCAPE = """
subs = ().__class__.__bases__[0].__subclasses__()
found = None
for c in subs:
    try:
        g = c.__init__.__globals__
    except Exception:
        continue
    if isinstance(g.get('__builtins__'), dict):
        found = g['__builtins__']
        break
RESULT = {'has_open': 'open' in found, 'has_import': '__import__' in found} if found else None
"""


def test_introspection_recovers_real_builtins() -> None:
    """Document the limitation: object introspection escapes the whitelist."""
    executor = PythonExecutor(time_limit_seconds=10)
    result = executor.execute(_INTROSPECTION_ESCAPE)
    # The whitelist does NOT hold against introspection — this is expected and
    # is exactly why run_python is gated behind hardened isolation (not yet
    # implemented).
    assert result == {"has_open": True, "has_import": True}


def test_introspection_can_read_file(tmp_path: Path) -> None:
    """Demonstrate the end-to-end consequence of the limitation (read a file)."""
    from pathlib import Path

    secret = Path(tmp_path) / "secret.txt"
    secret.write_text("top-secret")
    executor = PythonExecutor(time_limit_seconds=10)
    code = (
        "subs = ().__class__.__bases__[0].__subclasses__()\n"
        "found = None\n"
        "for c in subs:\n"
        "    try:\n"
        "        g = c.__init__.__globals__\n"
        "    except Exception:\n"
        "        continue\n"
        "    if isinstance(g.get('__builtins__'), dict):\n"
        "        found = g['__builtins__']\n"
        "        break\n"
        f"RESULT = found['open']({str(secret)!r}).read().strip() if found else None\n"
    )
    result = executor.execute(code)
    assert result == "top-secret"
