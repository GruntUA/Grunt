"""Idempotent POSTs - a retried create must not create a second document.

A client that may resend a POST (the offline queue replaying a create whose
first attempt's response was lost) sends ``Idempotency-Key: <uuid>``. The first
successful (2xx) response is remembered per (user, key) for a day and returned
as-is for any repeat, without running the request again.

Stored in Redis when configured, so a repeat that lands on another web worker
is answered too; without Redis (one process) in this process's memory.
"""

import json
import time
from collections import OrderedDict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

lazy from grunt.auth.service import decode_access_token
lazy from grunt.utils.redis import shared

_TTL_SECONDS = 24 * 3600
_MAX_ENTRIES = 5000

# status code, body, media type
Stored = tuple[int, bytes, str]


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._seen: OrderedDict[str, tuple[float, Stored]] = OrderedDict()

    def _user(self, request: Request) -> str | None:
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return None

        payload = decode_access_token(auth[7:])
        return payload.get("sub") if payload else None

    async def _get(self, cache_key: str) -> Stored | None:
        r = shared.get()
        if r is not None:
            try:
                raw = await r.get(cache_key)
            except Exception as exc:
                shared.failed("idempotency.redis_get_failed", exc)
            else:
                if not raw:
                    return None
                if isinstance(raw, str):
                    raw = raw.encode()
                head, _, body = raw.partition(b"\n")
                status_code, media_type = json.loads(head)
                return status_code, body, media_type
        hit = self._seen.get(cache_key)
        if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
            return hit[1]
        return None

    async def _put(self, cache_key: str, stored: Stored) -> None:
        r = shared.get()
        if r is not None:
            status_code, body, media_type = stored
            head = json.dumps([status_code, media_type]).encode()
            try:
                await r.set(cache_key, head + b"\n" + body, ex=_TTL_SECONDS)
                return
            except Exception as exc:
                shared.failed("idempotency.redis_set_failed", exc)
        self._seen[cache_key] = (time.monotonic(), stored)
        while len(self._seen) > _MAX_ENTRIES:
            self._seen.popitem(last=False)

    async def dispatch(self, request: Request, call_next) -> Response:
        key = request.headers.get("idempotency-key")
        if request.method != "POST" or not key:
            return await call_next(request)
        user = self._user(request)
        if not user:
            return await call_next(request)

        cache_key = f"idem:{request.headers.get('host', '')}|{user}|{key[:200]}"
        hit = await self._get(cache_key)
        if hit is not None:
            status_code, body, media_type = hit
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
            await self._put(cache_key, (response.status_code, body, media_type))
            return Response(body, status_code=response.status_code, headers=dict(response.headers))
        return response
