"""WebSocket endpoints for real-time document updates."""

from __future__ import annotations

import json
import structlog

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = structlog.get_logger()

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, channel: str) -> None:
        await ws.accept()
        self._connections.setdefault(channel, []).append(ws)
        logger.debug("ws.connect", channel=channel, total=len(self._connections.get(channel, [])))

    def disconnect(self, ws: WebSocket, channel: str) -> None:
        conns = self._connections.get(channel, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, channel: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        message = json.dumps({"event": event, "data": data})
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(channel, [])):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    async def broadcast_doc(self, doctype: str, doc_id: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        await self.broadcast(f"doc:{doctype}:{doc_id}", event, data)

    async def broadcast_list(self, doctype: str, event: str, data: dict) -> None:  # type: ignore[type-arg]
        await self.broadcast(f"list:{doctype}", event, data)


manager = ConnectionManager()


async def _authenticate_ws(websocket: WebSocket, token: str | None) -> bool:
    """Validate JWT token for WebSocket connections. Returns True if valid."""
    if not token:
        await websocket.close(code=4001)
        return False
    try:
        from grunt.config import settings  # noqa: PLC0415
        from jose import jwt, JWTError  # noqa: PLC0415

        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if not payload.get("sub"):
            raise ValueError("No subject in token")
        return True
    except Exception:  # noqa: BLE001
        await websocket.close(code=4001)
        return False


@router.websocket("/ws/{doctype}/{doc_id}")
async def ws_document(
    websocket: WebSocket,
    doctype: str,
    doc_id: str,
    token: str | None = Query(default=None),
) -> None:
    """Subscribe to changes on a specific document."""
    if not await _authenticate_ws(websocket, token):
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
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/ws/{doctype}")
async def ws_list(
    websocket: WebSocket,
    doctype: str,
    token: str | None = Query(default=None),
) -> None:
    """Subscribe to list-level changes for a DocType."""
    if not await _authenticate_ws(websocket, token):
        return
    channel = f"list:{doctype}"
    await manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
