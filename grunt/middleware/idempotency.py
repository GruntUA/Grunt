"""Idempotent POSTs - a retried create must not create a second document.

A client that may resend a POST (the offline queue replaying a create whose
first attempt's response was lost) sends ``Idempotency-Key: <uuid>``. The first
successful (2xx) response is remembered per (user, key) for a day and returned
as-is for any repeat, without running the request again.

In-process memory: correct for a single worker (the current deployment); with
several workers a repeat that lands on another worker is executed again.
"""

from __future__ import annotations

import time
from collections import OrderedDict

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from grunt.config import settings

_TTL_SECONDS = 24 * 3600
_MAX_ENTRIES = 5000


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._seen: OrderedDict[tuple[str, str], tuple[float, int, bytes, str]] = OrderedDict()

    def _user(self, request: Request) -> str | None:
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return None
        try:
            payload = jwt.decode(auth[7:], settings.secret_key, algorithms=[settings.algorithm])
        except jwt.PyJWTError:
            return None
        return payload.get("sub")

    async def dispatch(self, request: Request, call_next) -> Response:
        key = request.headers.get("idempotency-key")
        if request.method != "POST" or not key:
            return await call_next(request)
        user = self._user(request)
        if not user:
            return await call_next(request)

        now = time.monotonic()
        cache_key = (f"{request.headers.get('host', '')}|{user}", key[:200])
        hit = self._seen.get(cache_key)
        if hit and now - hit[0] < _TTL_SECONDS:
            _, status_code, body, media_type = hit
            return Response(
                body,
                status_code=status_code,
                media_type=media_type,
                headers={"Idempotent-Replay": "true"},
            )

        response = await call_next(request)
        if 200 <= response.status_code < 300:
            # call_next hands back a streaming response, typed as a plain Response.
            body = b"".join([chunk async for chunk in response.body_iterator])  # pyright: ignore[reportAttributeAccessIssue]
            media_type = response.media_type or response.headers.get(
                "content-type", "application/json"
            )
            self._seen[cache_key] = (now, response.status_code, body, media_type)
            while len(self._seen) > _MAX_ENTRIES:
                self._seen.popitem(last=False)
            return Response(body, status_code=response.status_code, headers=dict(response.headers))
        return response
