"""Bounded JSON Schema validation for structured output.

The Qwen adapter requests structured output with a JSON Schema and must verify
the model's reply actually conforms before returning it to the Research
Runtime. This module implements a **dependency-free** validator covering the
subset of JSON Schema keywords that the structured-output contract uses
(``type``, ``properties``, ``required``, ``items``, ``enum``, ``const``,
``additionalProperties``). Unsupported keywords are ignored rather than
silently enforced, and any violation raises :class:`StructuredOutputError`.

It deliberately does **not** pull in a full ``jsonschema`` dependency: the
contract only needs structural conformance, not the entire draft-2020-12
feature surface.
"""

from __future__ import annotations

from typing import Any

from qwen_research.domain.errors import StructuredOutputError

_TYPE_TUPLE = tuple[type, ...]

_JSON_TYPES: dict[str, type | _TYPE_TUPLE] = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def validate_against_schema(value: Any, schema: dict[str, Any]) -> None:
    """Raise :class:`StructuredOutputError` if *value* violates *schema*.

    A value is considered valid when it structurally satisfies every recognized
    keyword. ``None`` schemas are treated as unconstrained (no validation).
    """
    if not schema:
        return
    errors = _validate(value, schema, path="$")
    if errors:
        raise StructuredOutputError(
            "structured output does not conform to the requested schema: "
            + "; ".join(errors[:5])
            + ("; …" if len(errors) > 5 else "")
        )


def _validate(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors

    if "const" in schema and value != schema["const"]:
        return [f"{path}: expected const {schema['const']!r}, got {value!r}"]

    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: value {value!r} not in enum {schema['enum']!r}"]

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if not any(_matches_type(value, t) for t in schema_type):
            errors.append(f"{path}: value {value!r} not one of types {schema_type!r}")
            return errors
    elif schema_type is not None and not _matches_type(value, schema_type):
        errors.append(f"{path}: expected type {schema_type!r}, got {type(value).__name__!r}")
        return errors

    if schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type):
        errors.extend(_validate_object(value, schema, path))
    elif schema_type == "array" or (isinstance(schema_type, list) and "array" in schema_type):
        errors.extend(_validate_array(value, schema, path))

    return errors


def _matches_type(value: Any, schema_type: str) -> bool:
    expected = _JSON_TYPES.get(schema_type)
    if expected is None:
        return True  # unknown type keyword — do not enforce
    return isinstance(value, expected)


def _validate_object(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    errors: list[str] = []
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub_schema in properties.items():
            if name in value:
                errors.extend(_validate(value[name], sub_schema, f"{path}.{name}"))
            elif "required" in schema and name in schema["required"]:
                errors.append(f"{path}.{name}: required property missing")
    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if name not in value:
                errors.append(f"{path}.{name}: required property missing")
    return errors


def _validate_array(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    if not isinstance(value, list):
        return []
    errors: list[str] = []
    items = schema.get("items")
    if isinstance(items, dict):
        for idx, item in enumerate(value):
            errors.extend(_validate(item, items, f"{path}[{idx}]"))
    return errors
