"""Stable, deterministic, version-aware serialization for domain objects.

The serializer is deliberately small and transport-neutral: it encodes
dataclasses (including nested dataclasses, enums, ``Optional`` values, lists,
dicts, and timezone-aware datetimes) into a JSON-ready structure and back.

Properties guaranteed by this module:

* **Deterministic** — dictionary keys are sorted at encode time.
* **Version-aware** — every payload carries a ``schema_version`` field.
* **Type-safe on load** — the root object's type is recorded and resolved
  through the registry populated by :func:`serializable`.
* **No provider/transport fields** — nothing MCP-, Qwen-, or database-specific
  is ever serialized.
* **No hidden chain-of-thought** — the domain model has no such field, and this
  module will not invent one.
"""

from __future__ import annotations

import dataclasses
import datetime as _datetime
import enum
import json
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

SCHEMA_VERSION = 1

#: Qualified-name → type registry, populated by :func:`serializable`.
_TYPE_REGISTRY: dict[str, type[Any]] = {}


def serializable(cls: type[Any]) -> type[Any]:
    """Class decorator registering a domain type for round-trip serialization."""
    _TYPE_REGISTRY[f"{cls.__module__}.{cls.__qualname__}"] = cls
    return cls


def _qualname(cls: type[Any]) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def to_jsonable(obj: Any) -> Any:
    """Recursively convert *obj* into JSON-compatible primitives."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, _datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(item) for item in obj]
    return obj


def dumps(obj: Any, *, indent: int | None = None) -> str:
    """Serialize *obj* to a deterministic, versioned JSON string."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": _qualname(type(obj)),
        "data": to_jsonable(obj),
    }
    return json.dumps(payload, sort_keys=True, indent=indent)


def loads(text: str) -> Any:
    """Deserialize a string produced by :func:`dumps` back into a domain object."""
    payload = json.loads(text)
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {version!r} (expected {SCHEMA_VERSION})"
        )
    type_name = payload.get("type")
    if not isinstance(type_name, str) or type_name not in _TYPE_REGISTRY:
        raise ValueError(f"unknown serialized type {type_name!r}")
    return from_jsonable(payload.get("data"), _TYPE_REGISTRY[type_name])


def from_jsonable(data: Any, target: Any) -> Any:
    """Reconstruct *data* according to the type annotation *target*."""
    if target is Any or target is None:
        return data
    if data is None:
        return None

    # Optional[X] / Union[X, None]
    origin = get_origin(target)
    if origin is Union:
        args = get_args(target)
        non_none = [a for a in args if a is not type(None)]
        return from_jsonable(data, non_none[0]) if non_none else None

    # Enums are reconstructed from their value.
    if isinstance(target, type) and issubclass(target, enum.Enum):
        return target(data)

    # Timezone-aware datetimes.
    if target is _datetime.datetime:
        return _datetime.datetime.fromisoformat(data)

    # Nested dataclasses (``target`` is always a class here — it originates
    # from a type annotation).
    if dataclasses.is_dataclass(target):
        cls = cast(type[Any], target)
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(cls):
            if field.name in data:
                kwargs[field.name] = from_jsonable(data[field.name], hints.get(field.name, Any))
        return cls(**kwargs)

    # Generic containers.
    if origin in (list, tuple):
        args = get_args(target)
        # tuple[X, ...] yields (X, Ellipsis); plain list[X] yields (X,).
        item_type = args[0] if args else Any
        items = [from_jsonable(item, item_type) for item in data]
        return tuple(items) if origin is tuple else items
    if origin is dict:
        (_, value_type) = get_args(target) or (str, Any)
        return {key: from_jsonable(value, value_type) for key, value in data.items()}

    # Primitives and NewType-erased strings pass through.
    return data
