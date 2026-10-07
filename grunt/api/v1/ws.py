"""WebSocket endpoints for real-time document updates and user notifications."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import grunt
from grunt import log
from grunt.auth.doctypes.UserSession.user_session import client_ip

router = APIRouter()

# The browser WebSocket API can't set headers, so the client offers the JWT as
# the second subprotocol: ``Sec-WebSocket-Protocol: grunt.auth, <jwt>``. Unlike
# a ``?token=`` query param it never ends up in access logs. The server answers
# with ``grunt.auth`` only - the token is not echoed back.
AUTH_SUBPROTOCOL = "grunt.auth"


class ConnectionManager:
    """Manages WebSocket connections with optional Redis Pub/Sub fan-out.

    When Redis is configured, every ``broadcast`` / ``send_to_user`` call
    publishes to a Redis channel so that all worker instances can relay
    the message to their locally-connected clients.

    Channel naming:
      ``grunt:ws:<channel>``  ->  delivered to all connections on that channel

    Presence / field-lock state is kept **in-process** (per worker).
    For multi-worker deployments the presence_update event is published via
    Redis so all instances stay in sync, but each instance maintains its own
    view of who is connected locally.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        # channel -> {ws_id: user_info}
        self._presence: dict[str, dict[int, dict[str, str]]] = {}
        # channel -> {fieldname: user_info}
        self._field_locks: dict[str, dict[str, dict[str, str]]] = {}
        # Strong reference: asyncio keeps only weak ones, so an unreferenced
        # listener task can be garbage-collected mid-flight - realtime then
        # silently stops relaying.
        self._redis_listener_task: asyncio.Task[None] | None = None

    def _total_connections(self) -> int:
        return sum(len(v) for v in self._connections.values())

    async def connect(self, ws: WebSocket, channel: str, subprotocol: str | None = None) -> None:
        await ws.accept(subprotocol=subprotocol)
        self._connections.setdefault(channel, []).append(ws)
        await self.ensure_redis_listener()
        log.debug("ws.connect", channel=channel, ip=client_ip(ws), total=self._total_connections())

    def disconnect(self, ws: WebSocket, channel: str) -> None:
        conns = self._connections.get(channel, [])
        if ws in conns:
            conns.remove(ws)

    async def _send(self, channel: str, message: str) -> None:
        """Send a message to all connections on a channel, removing dead ones."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(channel, [])):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    # Redis helpers

    async def _redis_publish(self, channel: str, message: str) -> bool:
        """Publish a message to a Redis channel (best-effort); True if published."""
        try:
            from grunt.config import settings

            if not settings.redis_url:
                return False
            from grunt.utils.redis import connect

            r = connect(socket_connect_timeout=1)
            await r.publish(f"grunt:ws:{channel}", message)
            await r.aclose()
            return True
        except Exception:
            log.exception("suppressed_error")
            return False

    async def _deliver(self, channel: str, message: str) -> None:
        """Deliver to every process's clients on *channel*, exactly once.

        With Redis, publishing is enough: every web process - this one too -
        relays it to its own connections from the listener. Sending locally as
        well delivered each message twice. Without Redis (or if the publish
        failed) only this process's connections can be reached.
        """
        if not await self._redis_publish(channel, message):
            await self._send(channel, message)

    @property
    def redis_listener_alive(self) -> bool:
        task = self._redis_listener_task
        return task is not None and not task.done()

    async def ensure_redis_listener(self) -> None:
        """Start the Redis subscriber background task (once per process;
        again if it ever stopped)."""
        if self.redis_listener_alive:
            return
        try:
            from grunt.config import settings

            if not settings.redis_url:
                return
            self._redis_listener_task = asyncio.create_task(self._redis_listener_loop())
        except Exception:
            log.exception("suppressed_error")

    async def _redis_listener_loop(self) -> None:
        """Subscribe to grunt:ws:* and relay messages to local connections."""
        while True:
            try:
                from grunt.utils.redis import connect

                r = connect()
                pubsub = r.pubsub()
                await pubsub.psubscribe("grunt:ws:*")
                async for msg in pubsub.listen():
                    if msg["type"] != "pmessage":
                        continue
                    full_key: str = (
                        msg["channel"].decode()
                        if isinstance(msg["channel"], bytes)
                        else msg["channel"]
                    )
                    channel = full_key.removeprefix("grunt:ws:")
                    data: str = (
                        msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
                    )
                    if channel == "__broadcast_users__":
                        await self._handle_broadcast_users(data)
                    else:
                        await self._send(channel, data)
            except Exception as e:
                log.warning("ws.redis_listener_error", error=str(e))
                await asyncio.sleep(2)  # retry after brief pause

    # Public broadcast API

    async def broadcast(self, channel: str, event: str, data: dict[str, Any]) -> None:
        message = json.dumps({"event": event, "data": data})
        await self._deliver(channel, message)

    async def broadcast_doc(
        self, doctype: str, doc_id: str, event: str, data: dict[str, Any]
    ) -> None:
        await self.broadcast(f"doc:{doctype}:{doc_id}", event, data)

    async def broadcast_list(self, doctype: str, event: str, data: dict[str, Any]) -> None:
        await self.broadcast(f"list:{doctype}", event, data)

    async def send_to_user(self, user_email: str, payload: dict[str, Any]) -> None:
        """Send a message to all WebSocket connections of a specific user."""
        channel = f"user:{user_email}"
        message = json.dumps(payload)
        await self._deliver(channel, message)

    async def broadcast_all_users(self, payload: dict[str, Any]) -> None:
        """Broadcast a message to all connected user channels."""
        message = json.dumps(payload)
        if not await self._redis_publish("__broadcast_users__", message):
            await self._handle_broadcast_users(message)

    async def _handle_broadcast_users(self, message: str) -> None:
        """Called by the Redis listener for __broadcast_users__ channel."""
        for channel in list(self._connections):
            if channel.startswith("user:"):
                await self._send(channel, message)

    # Presence API

    def _presence_list(self, channel: str) -> list[dict[str, str]]:
        return list(self._presence.get(channel, {}).values())

    async def presence_join(self, channel: str, ws: WebSocket, user_info: dict[str, str]) -> None:
        self._presence.setdefault(channel, {})[id(ws)] = user_info
        await self._send(
            channel,
            json.dumps(
                {"event": "presence_update", "data": {"users": self._presence_list(channel)}}
            ),
        )

    async def presence_leave(self, channel: str, ws: WebSocket) -> None:
        presence = self._presence.get(channel, {})
        ws_id = id(ws)
        user_info = presence.pop(ws_id, None)
        if user_info is None:
            return

        # Release all field locks held by this connection
        locks = self._field_locks.get(channel, {})
        released = [f for f, u in list(locks.items()) if u.get("email") == user_info.get("email")]
        for field in released:
            locks.pop(field, None)
            await self._send(
                channel,
                json.dumps({"event": "field_unlocked", "data": {"field": field}}),
            )

        await self._send(
            channel,
            json.dumps(
                {"event": "presence_update", "data": {"users": self._presence_list(channel)}}
            ),
        )

    async def field_focus(self, channel: str, ws: WebSocket, fieldname: str) -> None:
        presence = self._presence.get(channel, {})
        user_info = presence.get(id(ws))
        if user_info is None:
            return
        self._field_locks.setdefault(channel, {})[fieldname] = user_info
        await self._send(
            channel,
            json.dumps({"event": "field_locked", "data": {"field": fieldname, "user": user_info}}),
        )

    async def field_blur(self, channel: str, fieldname: str) -> None:
        locks = self._field_locks.get(channel, {})
        if fieldname in locks:
            locks.pop(fieldname)
            await self._send(
                channel,
                json.dumps({"event": "field_unlocked", "data": {"field": fieldname}}),
            )


manager = ConnectionManager()


def _subprotocol_token(websocket: WebSocket) -> str | None:
    protocols = websocket.scope.get("subprotocols") or []
    if len(protocols) == 2 and protocols[0] == AUTH_SUBPROTOCOL:
        return protocols[1]
    return None


async def _authenticate_ws(websocket: WebSocket) -> str | None:
    """Validate the JWT offered via ``Sec-WebSocket-Protocol``.

    Returns the user email (subject) on success, or None on failure.
    """
    token = _subprotocol_token(websocket)
    if not token:
        log.info("ws.rejected", path=websocket.url.path, ip=client_ip(websocket), reason="no token")
        await websocket.close(code=4001)
        return None
    try:
        import jwt

        from grunt.config import settings

        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        sub = payload.get("sub")
        if not sub:
            raise ValueError("No subject in token")
        return sub
    except Exception as e:
        log.info("ws.rejected", path=websocket.url.path, ip=client_ip(websocket), reason=str(e))
        await websocket.close(code=4001)
        return None


async def _run_simple_channel(
    websocket: WebSocket, channel: str, subprotocol: str | None = None
) -> None:
    """Connect, relay ping/pong until disconnect - shared by ws_user/ws_site/ws_public.

    All three are the same channel lifecycle; they differ only in how
    *channel* is computed (and whether that requires authenticating first).
    """
    await manager.connect(websocket, channel, subprotocol)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except json.JSONDecodeError:
                log.debug("ws.invalid_json", raw=raw)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/ws/user")
async def ws_user(
    websocket: WebSocket,
) -> None:
    """Per-user channel for notifications and realtime messages."""
    user_email = await _authenticate_ws(websocket)
    if not user_email:
        return
    await _run_simple_channel(websocket, f"user:{user_email}", AUTH_SUBPROTOCOL)


@router.websocket("/ws/site")
async def ws_site(
    websocket: WebSocket,
) -> None:
    """Site-wide channel for authenticated users (activity feed, etc.).

    Declared before ``/ws/{doctype}`` so the literal path wins the match.
    """
    user_email = await _authenticate_ws(websocket)
    if not user_email:
        return
    await _run_simple_channel(websocket, "site", AUTH_SUBPROTOCOL)


@router.websocket("/ws/public/{channel:path}")
async def ws_public(
    websocket: WebSocket,
    channel: str,
) -> None:
    """Public (unauthenticated) channel for displays and kiosks."""
    await _run_simple_channel(websocket, f"public:{channel}")


@router.websocket("/ws/{doctype}/{doc_id}")
async def ws_document(
    websocket: WebSocket,
    doctype: str,
    doc_id: str,
) -> None:
    """Subscribe to changes on a specific document.

    Supports presence tracking and field-level locking.

    Client -> Server actions:
      { "action": "ping" }
      { "action": "presence_join", "user": { "email": "...", "full_name": "...", "color": "#..." } }
      { "action": "presence_leave" }
      { "action": "field_focus", "field": "fieldname" }
      { "action": "field_blur",  "field": "fieldname" }

    Server -> Client events:
      { "event": "pong" }
      { "event": "doc_change",       "data": { ... } }
      { "event": "presence_update",  "data": { "users": [...] } }
      { "event": "field_locked",     "data": { "field": "...", "user": { ... } } }
      { "event": "field_unlocked",   "data": { "field": "..." } }
    """
    user_email = await _authenticate_ws(websocket)
    if not user_email:
        return

    dt = await grunt.get_meta(doctype)
    normalized_doctype = dt.name if dt is not None else doctype

    channel = f"doc:{normalized_doctype}:{doc_id}"
    await manager.connect(websocket, channel, AUTH_SUBPROTOCOL)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.debug("ws.invalid_json", raw=raw)
                continue

            action = msg.get("action")
            if action == "ping":
                await websocket.send_text('{"event":"pong"}')
            elif action == "presence_join":
                user_info = msg.get("user") or {}
                await manager.presence_join(channel, websocket, user_info)
            elif action == "presence_leave":
                await manager.presence_leave(channel, websocket)
            elif action == "field_focus":
                fieldname = msg.get("field", "")
                if fieldname:
                    await manager.field_focus(channel, websocket, fieldname)
            elif action == "field_blur":
                fieldname = msg.get("field", "")
                if fieldname:
                    await manager.field_blur(channel, fieldname)

    except WebSocketDisconnect:
        await manager.presence_leave(channel, websocket)
        manager.disconnect(websocket, channel)


@router.websocket("/ws/{doctype}")
async def ws_list(
    websocket: WebSocket,
    doctype: str,
) -> None:
    """Subscribe to list-level changes for a DocType."""
    user_email = await _authenticate_ws(websocket)
    if not user_email:
        return

    dt = await grunt.get_meta(doctype)
    normalized_doctype = dt.name if dt is not None else doctype

    channel = f"list:{normalized_doctype}"
    await manager.connect(websocket, channel, AUTH_SUBPROTOCOL)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text('{"event":"pong"}')
            except json.JSONDecodeError:
                log.warning("json_decode_error_suppressed", exc_info=True)
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
