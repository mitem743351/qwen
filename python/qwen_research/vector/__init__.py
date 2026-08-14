"""Vector index layer: abstraction and the local SQLite backend."""

from qwen_research.vector.interface import VectorHit, VectorIndex, VectorRecord
from qwen_research.vector.sqlite import SqliteVectorIndex

__all__ = ["SqliteVectorIndex", "VectorHit", "VectorIndex", "VectorRecord"]
