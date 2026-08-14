"""Persistence contracts.

Only repository interfaces live here in Phase 1. Real persistence (SQLite,
PostgreSQL, DuckDB) is deferred; the in-memory implementations in
``qwen_research.research.state`` satisfy these interfaces for tests.
"""

from qwen_research.persistence.interfaces import (
    ArtifactRepository,
    ResearchStateRepository,
    SessionRepository,
    TaskRepository,
)

__all__ = [
    "ArtifactRepository",
    "ResearchStateRepository",
    "SessionRepository",
    "TaskRepository",
]
