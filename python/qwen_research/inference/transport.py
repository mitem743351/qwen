"""HTTP transport for the Qwen provider.

The transport is an injectable seam so tests can substitute a fake without a
live API key or network. The default implementation uses only the standard
library (``urllib``) — no third-party HTTP client and no OpenAI SDK.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from qwen_research.domain.errors import ProviderTimeoutError, ProviderUnavailableError

_STREAM_CHUNK_BYTES = 65536


@dataclasses.dataclass(frozen=True)
class TransportResponse:
    """A raw HTTP response (status + headers + bytes body)."""

    status: int
    headers: dict[str, str]
    body: bytes


@dataclasses.dataclass(frozen=True)
class StreamingResponse:
    """An HTTP response whose body is read incrementally (status + chunk iterator)."""

    status: int
    headers: dict[str, str]
    chunks: Iterator[bytes]


@runtime_checkable
class HttpTransport(Protocol):
    """Minimal HTTP surface the provider needs (method + path + body + auth)."""

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse: ...

    def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        idle_timeout_seconds: float,
    ) -> StreamingResponse:
        """Return an incrementally-read response body.

        The returned iterator enforces an **idle** timeout: if no bytes arrive
        for ``idle_timeout_seconds`` between chunks, it raises
        :class:`ProviderTimeoutError`.
        """
        ...


class UrllibHttpTransport:
    """A stdlib ``urllib`` implementation of :class:`HttpTransport`."""

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                return TransportResponse(
                    status=response.status,
                    headers=resp_headers,
                    body=response.read(),
                )
        except urllib.error.HTTPError as exc:
            # Surface the HTTP error so the provider can normalize status codes.
            resp_headers = {k.lower(): v for k, v in exc.headers.items()}
            return TransportResponse(status=exc.code, headers=resp_headers, body=exc.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError(f"provider unreachable: {exc}") from exc

    def stream(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: bytes,
        idle_timeout_seconds: float,
    ) -> StreamingResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=idle_timeout_seconds)
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in exc.headers.items()}
            return StreamingResponse(status=exc.code, headers=resp_headers, chunks=iter(()))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError(f"provider unreachable: {exc}") from exc

        resp_headers = {k.lower(): v for k, v in response.headers.items()}
        status = response.status
        return StreamingResponse(
            status=status,
            headers=resp_headers,
            chunks=_read_chunks(response, idle_timeout_seconds),
        )


def _read_chunks(response: Any, idle_timeout_seconds: float) -> Iterator[bytes]:
    """Yield raw body chunks, mapping an idle stall to :class:`ProviderTimeoutError`.

    ``urllib`` applies the socket timeout to each ``read()`` call, so a gap of
    more than ``idle_timeout_seconds`` between chunks surfaces as a
    ``TimeoutError`` (``socket.timeout`` is an alias of ``TimeoutError`` since
    Python 3.10).
    """
    read = response.read
    close = response.close
    try:
        while True:
            try:
                chunk = read(_STREAM_CHUNK_BYTES)
            except TimeoutError as exc:
                raise ProviderTimeoutError(
                    f"stream idle timeout exceeded ({idle_timeout_seconds}s)"
                ) from exc
            except OSError as exc:
                raise ProviderUnavailableError(f"stream read failed: {exc}") from exc
            if not chunk:
                return
            yield chunk
    finally:
        close()


def encode_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")
