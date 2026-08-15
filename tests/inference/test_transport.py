"""Stream-idle semantics and SSE line reassembly (Phase 8.1)."""

from __future__ import annotations

import pytest

from inference_helpers import make_provider, sse_response
from qwen_research.domain.errors import ProviderTimeoutError, ProviderUnavailableError
from qwen_research.domain.inference import InferencePolicy, InferenceRequest, StreamEventType
from qwen_research.inference.providers.qwen import _iter_sse_lines
from qwen_research.inference.transport import _read_chunks


def _request() -> InferenceRequest:
    from qwen_research.common.ids import TaskId

    return InferenceRequest(
        task_reference=TaskId("task_1"),
        inference_policy=InferencePolicy(),
        context=("question",),
    )


def test_stream_uses_idle_timeout() -> None:
    provider, transport = make_provider(
        lambda *_: sse_response({"choices": [{"delta": {"content": "hi"}}]})
    )
    list(provider.stream_events(_request()))
    assert transport.stream_calls, "streaming should use the incremental transport path"
    url, headers, body, idle = transport.stream_calls[0]
    assert body["stream"] is True
    assert idle == 30.0  # default stream_idle_seconds


def test_stream_events_via_stream_path() -> None:
    provider, _ = make_provider(
        lambda *_: sse_response(
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"finish_reason": "stop"}], "usage": {"total_tokens": 5}},
        )
    )
    events = list(provider.stream_events(_request()))
    text = "".join(e.text_delta for e in events if e.type is StreamEventType.TEXT_DELTA)
    assert text == "Hello"


def test_sse_lines_reassembled_across_chunks() -> None:
    first = b'data: {"choices": [{"delta": {"content": "He'
    second = b'llo"}}]}\n'
    chunks = iter([first, second, b"data: [DONE]\n"])
    lines = list(_iter_sse_lines(chunks))
    assert lines[0] == 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
    assert lines[1] == "data: [DONE]"


class _FakeChunkedResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._i = 0

    def read(self, _amt: int) -> bytes:
        if self._i < len(self._chunks):
            out = self._chunks[self._i]
            self._i += 1
            return out
        return b""

    def close(self) -> None:
        pass


def _fake_response(chunks: list[bytes]) -> _FakeChunkedResponse:
    return _FakeChunkedResponse(chunks)


def test_read_chunks_yields_and_closes() -> None:
    response = _fake_response([b"abc", b"def"])
    assert list(_read_chunks(response, 30.0)) == [b"abc", b"def"]


def test_read_chunks_maps_idle_timeout() -> None:
    class _TimeoutResp:
        def read(self, _amt: int) -> bytes:
            raise TimeoutError("timed out")

        def close(self) -> None:
            pass

    with pytest.raises(ProviderTimeoutError):
        list(_read_chunks(_TimeoutResp(), 30.0))


def test_read_chunks_maps_read_failure() -> None:
    class _BrokenResp:
        def read(self, _amt: int) -> bytes:
            raise OSError("reset")

        def close(self) -> None:
            pass

    with pytest.raises(ProviderUnavailableError):
        list(_read_chunks(_BrokenResp(), 30.0))
