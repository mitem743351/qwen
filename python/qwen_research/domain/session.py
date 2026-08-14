"""The Session domain object."""

from __future__ import annotations

import dataclasses
from datetime import datetime

from qwen_research.common.ids import SessionId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now
from qwen_research.domain.modes import OperatingMode


@serializable
@dataclasses.dataclass(frozen=True)
class Session:
    """A persistent interaction context binding tasks to a project and mode."""

    session_id: SessionId
    project_id: str
    created_at: datetime
    updated_at: datetime
    mode: OperatingMode
    metadata: dict[str, str] = dataclasses.field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        project_id: str = "default",
        mode: OperatingMode = OperatingMode.STUDIO_NATIVE,
        metadata: dict[str, str] | None = None,
    ) -> Session:
        now = utc_now()
        return cls(
            session_id=SessionId(new_id("session")),
            project_id=project_id,
            created_at=now,
            updated_at=now,
            mode=mode,
            metadata=dict(metadata or {}),
        )
