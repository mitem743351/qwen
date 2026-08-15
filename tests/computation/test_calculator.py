"""Safe arithmetic-expression evaluator tests."""

from __future__ import annotations

import pytest

from qwen_research.computation.calculator import calculate
from qwen_research.domain.errors import ComputationValidationError


def test_basic_arithmetic() -> None:
    assert calculate("1 + 2 * 3") == 7.0
    assert calculate("(1 + 2) * 3") == 9.0
    assert calculate("2 ** 3") == 8.0
    assert calculate("10 / 4") == 2.5


def test_math_functions() -> None:
    assert calculate("sqrt(16)") == 4.0
    assert calculate("abs(-3) + max(1, 5)") == 8.0


def test_constants() -> None:
    assert abs(calculate("pi") - 3.14159) < 1e-4


def test_variables() -> None:
    assert calculate("x + y", {"x": 2.0, "y": 3.0}) == 5.0


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd')",
        "eval('1+1')",
        "().__class__.__bases__",
        "import os",
        "'a' + 'b'",  # non-numeric
        "os.system('id')",
    ],
)
def test_rejects_unsafe_expressions(expression: str) -> None:
    with pytest.raises(ComputationValidationError):
        calculate(expression)
