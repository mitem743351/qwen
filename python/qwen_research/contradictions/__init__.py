"""Contradiction layer: model, deterministic detection, and assessment."""

from qwen_research.contradictions.assessment import ContradictionAssessment, assess_contradiction
from qwen_research.contradictions.detector import detect_contradiction, detect_contradictions
from qwen_research.contradictions.models import (
    Contradiction,
    ContradictionSeverity,
    ContradictionStatus,
    ContradictionType,
)

__all__ = [
    "Contradiction",
    "ContradictionAssessment",
    "ContradictionSeverity",
    "ContradictionStatus",
    "ContradictionType",
    "assess_contradiction",
    "detect_contradiction",
    "detect_contradictions",
]
