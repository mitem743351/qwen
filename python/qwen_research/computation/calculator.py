"""A safe arithmetic-expression evaluator (CALCULATE).

Evaluates a small, deterministic subset of Python expressions — numeric
literals, arithmetic operators, parentheses, and a fixed whitelist of ``math``
functions. It never evaluates arbitrary code, attribute access, calls, or
subscripts; ``ast`` is used only to *parse and walk* the tree, never ``eval``.
"""

from __future__ import annotations

import ast
import math
import operator

from qwen_research.domain.errors import ComputationValidationError

_BINOPS: dict[type[ast.operator], object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNOPS: dict[type[ast.unaryop], object] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_FUNCTIONS: dict[str, object] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": math.pow,
}

_ALLOWED_NAMES = set(_FUNCTIONS) | {"pi", "e", "tau"}

_CONSTANTS: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}


def calculate(expression: str, variables: dict[str, float] | None = None) -> float:
    """Evaluate a restricted arithmetic *expression*, returning a float.

    Variables (from explicit parameters) are looked up in *variables*; unknown
    names raise :class:`ComputationValidationError`.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ComputationValidationError(f"invalid expression: {exc.msg}") from exc
    try:
        value = _eval(tree.body, dict(variables or {}))
    except ComputationValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize arithmetic/domain errors
        raise ComputationValidationError(f"expression evaluation failed: {exc}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComputationValidationError("expression did not evaluate to a number")
    return float(value)


def _eval(node: ast.AST, variables: dict[str, float]) -> object:
    if isinstance(node, ast.Expression):
        return _eval(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ComputationValidationError("only numeric literals are allowed")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ComputationValidationError(f"unsupported operator {type(node.op).__name__}")
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        return op(left, right)  # type: ignore[operator]
    if isinstance(node, ast.UnaryOp):
        op = _UNOPS.get(type(node.op))
        if op is None:
            raise ComputationValidationError(f"unsupported unary operator {type(node.op).__name__}")
        return op(_eval(node.operand, variables))  # type: ignore[operator]
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise ComputationValidationError(f"unknown name {node.id!r}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ComputationValidationError("only named math functions are allowed")
        fn = _FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ComputationValidationError(f"function {node.func.id!r} is not allowed")
        args = [_eval(a, variables) for a in node.args]
        return fn(*args)  # type: ignore[operator]
    raise ComputationValidationError(f"unsupported expression node {type(node).__name__}")
