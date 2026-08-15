"""Python sandbox tests (subprocess isolation + restricted builtins)."""

from __future__ import annotations

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
