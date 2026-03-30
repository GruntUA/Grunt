"""WebSocket endpoints for real-time document updates and user notifications."""

from __future__ import annotations

import json
from typing import Any

import structlog

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = structlog.get_logger()

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections with optional Redis Pub/Sub fan-out.

    When Redis is configured, every ``broadcast`` / ``send_to_user`` call
    publishes to a Redis channel so that all worker instances can relay
    the message to their locally-connected clients.

    Channel naming:
      ``grunt:ws:<channel>``  →  delivered to all connections on that channel
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._redis_listener_started = False

    def _total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        self._connections.setdefault(channel, []).append(ws)
        await self.ensure_redis_listener()
        total = self._total_connections()
        logger.debug("ws.connect", channel=channel, total=total)
        try:
            from grunt.core.monitoring.metrics import ws_connections_active  # noqa: PLC0415
            if ws_connections_active is not None:
                ws_connections_active.set(total)
        except Exception:  # noqa: BLE001
            pass

    def disconnect(self, ws: WebSocket, channel: str) -> None:
        conns = self._connections.get(channel, [])
        if ws in conns:
            conns.remove(ws)
        total = self._total_connections()
        try:
            from grunt.core.monitoring.metrics import ws_connections_active  # noqa: PLC0415
            if ws_connections_active is not None:
                ws_connections_active.set(total)
        except Exception:  # noqa: BLE001
            pass

    async def _send(self, channel: str, message: str) -> None:
        """Send a message to all connections on a channel, removing dead ones."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(channel, [])):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    # ── Redis helpers ─────────────────────────────────────────────────

    async def _redis_publish(self, channel: str, message: str) -> None:
        """Publish a message to a Redis channel (best-effort)."""
        try:
            from grunt.config import settings  # noqa: PLC0415

            if not settings.redis_url:
                return
            import redis.asyncio as aioredis  # noqa: PLC0415

            r = aioredis.from_url(settings.redis_url, socket_connect_timeout=1)
            await r.publish(f"grunt:ws:{channel}", message)
            await r.aclose()
        except Exception:  # noqa: BLE001
            pass

    async def ensure_redis_listener(self) -> None:
        """Start the Redis subscriber background task (once per process)."""
        if self._redis_listener_started:
            return
        try:
            from grunt.config import settings  # noqa: PLC0415

            if not settings.redis_url:
                return
            import asyncio  # noqa: PLC0415

            self._redis_listener_started = True
            asyncio.create_task(self._redis_listener_loop())
        except Exception:  # noqa: BLE001
            pass

    async def _redis_listener_loop(self) -> None:
        """Subscribe to grunt:ws:* and relay messages to local connections."""
        import asyncio  # noqa: PLC0415

        while True:
            try:
                from grunt.config import settings  # noqa: PLC0415
                import redis.asyncio as aioredis  # noqa: PLC0415

                r = aioredis.from_url(settings.redis_url)
                pubsub = r.pubsub()
                await pubsub.psubscribe("grunt:ws:*")
                async for msg in pubsub.listen():
                    if msg["type"] != "pmessage":
                        continue
                    full_key: str = msg["channel"].decode() if isinstance(msg["channel"], bytes) else msg["channel"]
                    channel = full_key.removeprefix("grunt:ws:")
                    data: str = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
                    if channel == "__broadcast_users__":
                        await self._handle_broadcast_users(data)
                    else:
                        await self._send(channel, data)
            except Exception:  # noqa: BLE001
                await asyncio.sleep(2)  # retry after brief pause

    # ── Public broadcast API ──────────────────────────────────────────

    async def broadcast(self, channel: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        message = json.dumps({"event": event, "data": data})
        await self._redis_publish(channel, message)
        await self._send(channel, message)

    async def broadcast_doc(self, doctype: str, doc_id: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        await self.broadcast(f"doc:{doctype}:{doc_id}", event, data)

    async def broadcast_list(self, doctype: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        await self.broadcast(f"list:{doctype}", event, data)

    async def send_to_user(self, user_email: str, payload: dict[str, Any]) -> None:
        """Send a message to all WebSocket connections of a specific user."""
        channel = f"user:{user_email}"
        message = json.dumps(payload)
        await self._redis_publish(channel, message)
        await self._send(channel, message)

    async def broadcast_all_users(self, payload: dict[str, Any]) -> None:
        """Broadcast a message to all connected user channels."""
        message = json.dumps(payload)
        # Local delivery
        for channel in list(self._connections):
            if channel.startswith("user:"):
                await self._send(channel, message)
        # Redis fan-out to other instances via a dedicated broadcast channel
        await self._redis_publish("__broadcast_users__", message)

    async def _handle_broadcast_users(self, message: str) -> None:
        """Called by the Redis listener for __broadcast_users__ channel."""
        for channel in list(self._connections):
            if channel.startswith("user:"):
                await self._send(channel, message)


manager = ConnectionManager()


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> str | None:
    """Validate JWT token for WebSocket connections.

    Returns the user email (subject) on success, or None on failure.
    """
    if not token:
        await websocket.close(code=4001)
        return None
    try:
        import jwt  # noqa: PLC0415
        from grunt.config import settings  # noqa: PLC0415

        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        sub = payload.get("sub")
        if not sub:
            raise ValueError("No subject in token")
        return sub
    except Exception:  # noqa: BLE001
        await websocket.close(code=4001)
        return None


@router.websocket("/ws/user")
async def ws_user(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> None:
    """Per-user channel for notifications and realtime messages.

    All persistent notifications and transient messages (toasts, alerts)
    are delivered through this channel.
    """
    user_email = await _authenticate_ws(websocket, token)
    if not user_email:
        return
    channel = f"user:{user_email}"
    await manager.connect(websocket, channel)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except json.JSONDecodeError:
                logger.debug("ws.invalid_json", raw=raw)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/ws/public/{channel:path}")
async def ws_public(
    websocket: WebSocket,
    channel: str,
) -> None:
    """Public (unauthenticated) channel for displays and kiosks.

    Apps broadcast to these channels via ``publish_channel()``.
    Example: ``/ws/public/queue:board`` subscribes to queue board updates.
    """
    full_channel = f"public:{channel}"
    await manager.connect(websocket, full_channel)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except json.JSONDecodeError:
                logger.debug("ws.invalid_json", raw=raw)
    except WebSocketDisconnect:
        manager.disconnect(websocket, full_channel)


@router.websocket("/ws/{doctype}/{doc_id}")
async def ws_document(
    websocket: WebSocket,
    doctype: str,
    doc_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Subscribe to changes on a specific document."""
    user_email = await _authenticate_ws(websocket, token)
    if not user_email:
        return
    channel = f"doc:{doctype}:{doc_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except json.JSONDecodeError:
                logger.debug("ws.invalid_json", raw=raw)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/ws/{doctype}")
async def ws_list(
    websocket: WebSocket,
    doctype: str,
    token: str | None = Query(default=None),
) -> None:
    """Subscribe to list-level changes for a DocType."""
    user_email = await _authenticate_ws(websocket, token)
    if not user_email:
        return
    channel = f"list:{doctype}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
