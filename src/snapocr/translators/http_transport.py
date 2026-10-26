"""Thin loopback HTTP transport (D3, D9). The only module in snapocr that imports ``http.client``.

``http.client`` instead of ``urllib.request``: it never reads system proxy
settings and never follows redirects, either of which could take a request
off 127.0.0.1. One fresh connection per call, closed afterwards, so calls from
several threads share no state.
"""

from __future__ import annotations

import http.client

from snapocr.translators.config import Endpoint
from snapocr.translators.errors import ErrorContext, TranslationError, TranslationErrorKind
from snapocr.translators.protocol import ChatRequest

DEFAULT_MAX_RESPONSE_BYTES = 1_048_576


def post_json(
    endpoint: Endpoint,
    request: ChatRequest,
    timeout_s: float,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    *,
    ctx: ErrorContext,
) -> tuple[int, bytes]:
    """POST ``request`` and return ``(status, body)``; any status is returned as is.

    ``timeout_s`` bounds each socket operation (connect, every read), not the total (D9).
    """
    if type(endpoint) is not Endpoint:  # defence in depth: only validated loopback endpoints
        raise TypeError(f"endpoint: expected Endpoint, got {type(endpoint).__name__}")

    failure: tuple[TranslationErrorKind, str] | None = None
    status, body = 0, b""
    conn = http.client.HTTPConnection(endpoint.host, endpoint.port, timeout=timeout_s)
    try:
        conn.request("POST", request.path, body=request.body, headers=dict(request.headers))
        response = conn.getresponse()
        status = response.status
        # Read at most one byte past the limit: never buffer an oversized body.
        body = response.read(max_response_bytes + 1)
        # read(amt) returns a short body at EOF instead of raising; a declared
        # Content-Length that was not met is still a truncated response.
        if len(body) <= max_response_bytes and response.length:
            raise http.client.IncompleteRead(b"", response.length)
    except ConnectionRefusedError:
        failure = (TranslationErrorKind.UNREACHABLE, "ConnectionRefusedError")
    except TimeoutError:
        failure = (TranslationErrorKind.TIMEOUT, "TimeoutError")
    except (OSError, http.client.HTTPException) as exc:
        # Only the type name: e.g. BadStatusLine.args holds the received line.
        failure = (TranslationErrorKind.CONNECTION, type(exc).__name__)
    finally:
        conn.close()

    # Raised outside the except blocks so no transport exception hangs on __context__ (Q12).
    if failure is not None:
        kind, detail = failure
        raise TranslationError(kind, base_url=ctx.base_url, model=ctx.model, detail=detail)
    if len(body) > max_response_bytes:
        raise TranslationError(
            TranslationErrorKind.BAD_RESPONSE,
            base_url=ctx.base_url,
            model=ctx.model,
            detail=f"body exceeds {max_response_bytes} bytes",
        )
    return status, body
