"""Neutral capability registry.

The planner can query capability availability; MCP is **not** the capability
registry (and the registry is not coupled to MCP).
"""

from __future__ import annotations

from qwen_research.domain.errors import ConfigurationError
from qwen_research.orchestration.models import ResearchCapability


class CapabilityRegistry:
    """A name-keyed registry of research capabilities."""

    def __init__(self, capabilities: dict[str, ResearchCapability] | None = None) -> None:
        self._capabilities = dict(capabilities or {})

    def register(self, capability: ResearchCapability) -> None:
        if capability.name in self._capabilities:
            raise ConfigurationError(
                f"capability {capability.name!r} is already registered"
            )
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> ResearchCapability:
        try:
            return self._capabilities[name]
        except KeyError:
            raise ConfigurationError(f"unknown capability {name!r}") from None

    def available(self, name: str) -> bool:
        return name in self._capabilities and self._capabilities[name].availability == "available"

    def list(self) -> tuple[ResearchCapability, ...]:
        return tuple(sorted(self._capabilities.values(), key=lambda c: c.name))


def capability_registry_from_runtime(
    *,
    retriever: bool,
    memory: bool,
    verification: bool,
    computation: bool,
) -> CapabilityRegistry:
    """Build a registry reflecting which subsystems are wired into the runtime."""

    def cap(name: str, description: str, permission: str, present: bool) -> ResearchCapability:
        return ResearchCapability(
            name=name,
            description=description,
            required_permission=permission,
            availability="available" if present else "unavailable",
        )

    return CapabilityRegistry(
        {
            "retrieval": cap(
                "retrieval", "corpus evidence retrieval", "read", retriever
            ),
            "memory": cap(
                "memory", "persistent structured research memory", "write", memory
            ),
            "verification": cap(
                "verification", "claim verification and contradictions", "analyze",
                verification,
            ),
            "computation": cap(
                "computation", "deterministic DuckDB/Python computation", "analyze",
                computation,
            ),
            "artifact": cap(
                "artifact", "artifact storage and provenance", "write", True
            ),
            "inference": cap(
                "inference", "future model execution boundary", "analyze", False
            ),
        }
    )
