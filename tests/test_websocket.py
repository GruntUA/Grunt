"""WebSockets: the user channel handshake, ping/pong, and exactly-once delivery
of server pushes (the «Стан системи» report checks the same in the browser)."""

from __future__ import annotations

import json

import jwt
import pytest
from starlette.testclient import TestClient

from grunt.api.v1.ws import AUTH_SUBPROTOCOL, manager
from grunt.config import settings
from grunt.main import app


def _token(sub: str) -> str:
    return jwt.encode({"sub": sub}, settings.secret_key, algorithm=settings.algorithm)


def test_user_channel_ping_pong():
    with TestClient(app).websocket_connect(
        "/api/v1/ws/user", subprotocols=[AUTH_SUBPROTOCOL, _token("a@x.com")]
    ) as ws:
        assert ws.accepted_subprotocol == AUTH_SUBPROTOCOL  # the token is not echoed back
        ws.send_text(json.dumps({"action": "ping"}))
        assert ws.receive_json() == {"event": "pong"}


@pytest.mark.parametrize("subprotocols", [None, [AUTH_SUBPROTOCOL, "forged"]])
def test_user_channel_rejects_missing_or_bad_token(subprotocols):
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        TestClient(app).websocket_connect("/api/v1/ws/user", subprotocols=subprotocols) as ws,
    ):
        ws.receive_text()
    assert exc.value.code == 4001


def test_query_token_is_ignored():
    """``?token=`` leaked the JWT into access logs - it no longer authenticates."""
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        TestClient(app).websocket_connect(f"/api/v1/ws/user?token={_token('a@x.com')}") as ws,
    ):
        ws.receive_text()


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self, subprotocol: str | None = None) -> None: ...

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


@pytest.fixture
def user_socket():
    ws = _FakeSocket()
    channel = "user:admin@grunt.example.com"
    manager._connections.setdefault(channel, []).append(ws)
    yield ws
    manager.disconnect(ws, channel)


@pytest.mark.asyncio
async def test_ws_echo_arrives_exactly_once(client, auth_headers, user_socket, monkeypatch):
    monkeypatch.setattr(settings, "redis_url", None)
    r = await client.post(
        "/api/v1/method/grunt.monitoring.health.ws_echo",
        json={"nonce": "n1"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert user_socket.sent == [{"event": "health_echo", "data": {"nonce": "n1"}}]


@pytest.mark.asyncio
async def test_published_via_redis_is_not_also_sent_locally(user_socket, monkeypatch):
    """With Redis the listener relays to this process's sockets too — sending
    locally as well used to deliver every message twice."""
    published = []

    async def fake_publish(channel, message):
        published.append(channel)
        return True

    monkeypatch.setattr(manager, "_redis_publish", fake_publish)
    await manager.send_to_user("admin@grunt.example.com", {"event": "x"})
    await manager.broadcast("user:admin@grunt.example.com", "y", {})
    assert published == ["user:admin@grunt.example.com"] * 2
    assert user_socket.sent == []


@pytest.mark.asyncio
async def test_failed_redis_publish_falls_back_to_local(user_socket, monkeypatch):
    async def failed_publish(channel, message):
        return False

    monkeypatch.setattr(manager, "_redis_publish", failed_publish)
    await manager.send_to_user("admin@grunt.example.com", {"event": "x"})
    assert user_socket.sent == [{"event": "x"}]
