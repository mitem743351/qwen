"""Typed configuration contracts.

Phase 1 defines a stable configuration *model* only. Environment-variable and
config-file loading are introduced in later phases.
"""

from __future__ import annotations

import dataclasses

from qwen_research.common.serialization import serializable


@serializable
@dataclasses.dataclass(frozen=True)
class SystemConfig:
    """System-level configuration."""

    name: str = "qwen-research"
    log_level: str = "info"


@serializable
@dataclasses.dataclass(frozen=True)
class ReasoningConfig:
    """Reasoning defaults."""

    default_profile: str = "DEEP"


@serializable
@dataclasses.dataclass(frozen=True)
class RuntimeConfig:
    """Runtime defaults."""

    default_mode: str = "studio_native"
    default_project: str = "default"


@serializable
@dataclasses.dataclass(frozen=True)
class SecurityConfig:
    """Security posture defaults."""

    allow_write: bool = False
    allow_destructive: bool = False
    local_only: bool = True


@serializable
@dataclasses.dataclass(frozen=True)
class PathsConfig:
    """Filesystem paths (logical; not necessarily materialized in Phase 1)."""

    corpus: str = "corpus"
    data: str = "data"
    artifacts: str = "artifacts"
    workspace: str = "workspace"


@serializable
@dataclasses.dataclass(frozen=True)
class Config:
    """The aggregate configuration model."""

    system: SystemConfig = dataclasses.field(default_factory=SystemConfig)
    reasoning: ReasoningConfig = dataclasses.field(default_factory=ReasoningConfig)
    runtime: RuntimeConfig = dataclasses.field(default_factory=RuntimeConfig)
    security: SecurityConfig = dataclasses.field(default_factory=SecurityConfig)
    paths: PathsConfig = dataclasses.field(default_factory=PathsConfig)
