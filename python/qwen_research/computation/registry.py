"""Internal computation-backend registry.

Couples operation kinds to execution backends without coupling either to MCP.
Future backends (Rust/GPU/remote) register here without touching the engine.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol, runtime_checkable

from qwen_research.computation.models import ComputationOperation
from qwen_research.domain.errors import ComputationValidationError


@runtime_checkable
class ExecutionBackend(Protocol):
    """A named execution backend with a declared operation capability."""

    name: str
    operations: frozenset[ComputationOperation]


@dataclasses.dataclass(frozen=True)
class BackendCapability:
    """A backend's declared capability (exposed via ``list_capabilities``)."""

    name: str
    operations: tuple[str, ...]


class ComputationRegistry:
    """Maps operations to backends and lists capabilities."""

    def __init__(self) -> None:
        self._backends: dict[str, ExecutionBackend] = {}
        self._operation_backend: dict[ComputationOperation, str] = {}

    def register_backend(self, backend: ExecutionBackend) -> None:
        if backend.name in self._backends:
            raise ComputationValidationError(f"backend {backend.name!r} already registered")
        self._backends[backend.name] = backend
        for op in backend.operations:
            self._operation_backend[op] = backend.name

    def get_backend(self, name: str) -> ExecutionBackend:
        try:
            return self._backends[name]
        except KeyError:
            raise ComputationValidationError(f"unknown backend {name!r}") from None

    def backend_for(self, operation: ComputationOperation) -> str | None:
        return self._operation_backend.get(operation)

    def list_capabilities(self) -> list[BackendCapability]:
        return [
            BackendCapability(name=b.name, operations=tuple(sorted(o.value for o in b.operations)))
            for b in self._backends.values()
        ]
