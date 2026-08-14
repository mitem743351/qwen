"""Serialization determinism, version-awareness, and round-trips."""

from __future__ import annotations

import pytest

from qwen_research.common.ids import TaskId
from qwen_research.common.serialization import SCHEMA_VERSION, dumps, loads
from qwen_research.domain.reasoning import DEEP
from qwen_research.domain.research import Hypothesis, ResearchState
from qwen_research.domain.session import Session
from qwen_research.domain.source import Source, SourceType
from qwen_research.domain.task import TaskStatus


def test_dumps_is_deterministic() -> None:
    session = Session.create()
    assert dumps(session) == dumps(session)


def test_roundtrip_preserves_equality() -> None:
    source = Source.create("https://x.example/a", "A", SourceType.WEB, author="alice")
    assert loads(dumps(source)) == source


def test_roundtrip_nested_structures() -> None:
    state = ResearchState(
        task_id=TaskId("task_1"),
        current_stage=TaskStatus.PLANNED,
        hypotheses=(Hypothesis("h1"), Hypothesis("h2")),
    )
    assert loads(dumps(state)) == state


def test_roundtrip_enums_and_optional_datetimes() -> None:
    source = Source.create(
        "https://x.example/a", "A", SourceType.PAPER, publication_date=None
    )
    restored = loads(dumps(source))
    assert restored.source_type is SourceType.PAPER
    assert restored.publication_date is None


def test_roundtrip_reasoning_objects() -> None:
    assert loads(dumps(DEEP)) == DEEP
    assert loads(dumps(DEEP.budget())) == DEEP.budget()


def test_schema_version_present() -> None:
    payload = dumps(Session.create())
    assert '"schema_version": 1' in payload


def test_unknown_type_rejected() -> None:
    import json

    payload = json.dumps({"schema_version": SCHEMA_VERSION, "type": "no.such.Type", "data": {}})
    with pytest.raises(ValueError):
        loads(payload)


def test_unsupported_version_rejected() -> None:
    import json

    payload = json.dumps({"schema_version": 999, "type": "x", "data": {}})
    with pytest.raises(ValueError):
        loads(payload)
