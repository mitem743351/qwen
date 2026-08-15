"""Typed identifiers.

Identifiers are ``NewType`` wrappers over ``str`` so that distinct entity kinds
cannot be silently interchanged, while remaining trivially serializable (they
are plain strings at runtime). Use :func:`new_id` to mint a fresh identifier
and wrap it with the appropriate ``NewType``.
"""

from __future__ import annotations

from typing import NewType
from uuid import uuid4

TaskId = NewType("TaskId", str)
SessionId = NewType("SessionId", str)
SourceId = NewType("SourceId", str)
EvidenceId = NewType("EvidenceId", str)
ClaimId = NewType("ClaimId", str)
ArtifactId = NewType("ArtifactId", str)
WorkflowId = NewType("WorkflowId", str)
VerificationId = NewType("VerificationId", str)
VerificationReportId = NewType("VerificationReportId", str)
ContradictionId = NewType("ContradictionId", str)
EvidenceAssessmentId = NewType("EvidenceAssessmentId", str)
ComputationId = NewType("ComputationId", str)


def new_id(prefix: str) -> str:
    """Return a fresh, human-readable, unique identifier string.

    The returned value is an opaque ``str``; wrap it with the entity's
    ``NewType`` (e.g. ``TaskId(new_id("task"))``).
    """
    return f"{prefix}_{uuid4().hex}"
