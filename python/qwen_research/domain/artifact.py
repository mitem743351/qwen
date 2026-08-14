"""The Artifact domain object."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from qwen_research.common.ids import ArtifactId, SessionId, TaskId, new_id
from qwen_research.common.serialization import serializable
from qwen_research.common.timestamps import utc_now


class ArtifactType(StrEnum):
    """Kinds of generated output."""

    REPORT = "report"
    DATASET = "dataset"
    ANALYSIS = "analysis"
    NOTE = "note"
    OTHER = "other"


@serializable
@dataclasses.dataclass(frozen=True)
class Artifact:
    """A generated, provenance-tracked output."""

    artifact_id: ArtifactId
    artifact_type: ArtifactType
    path: str
    task_id: TaskId | None
    session_id: SessionId | None
    created_at: datetime
    provenance: dict[str, str]
    version: int

    @classmethod
    def create(
        cls,
        artifact_type: ArtifactType,
        path: str,
        *,
        task_id: TaskId | None = None,
        session_id: SessionId | None = None,
        provenance: dict[str, str] | None = None,
        version: int = 1,
    ) -> Artifact:
        return cls(
            artifact_id=ArtifactId(new_id("artifact")),
            artifact_type=artifact_type,
            path=path,
            task_id=task_id,
            session_id=session_id,
            created_at=utc_now(),
            provenance=dict(provenance or {}),
            version=version,
        )
