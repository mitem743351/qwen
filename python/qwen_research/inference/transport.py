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
from typing import Protocol, runtime_checkable

from qwen_research.domain.errors import ProviderUnavailableError


@dataclasses.dataclass(frozen=True)
class TransportResponse:
    """A raw HTTP response (status + headers + bytes body)."""

    status: int
    headers: dict[str, str]
    body: bytes


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


def encode_json(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True).encode("utf-8")
