"""Security PoC: subscribing to a document's realtime room (or a DocType's
list room) must require read access to it. A room carries doc_change payloads
and other users' presence, so a valid login alone must not be enough.

Exercises ``_ws_user_can_read`` directly (a full WebSocket handshake needs a
WS-capable client the suite doesn't have); the handlers call it and close with
code 4403 when it returns False.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from tests.support import make_user  # noqa: F401  (kept for parity with other tests)

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

SECRET = {
    "name": "WsSecret",
    "label": "Ws Secret",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Text"}],
    "permissions": [
        {"role": "Owner", "read": True, "write": True, "create": True, "match": "owner == user"},
    ],
}


class _StubWS:
    def __init__(self) -> None:
        self.headers = {"host": "__pytest__"}


def _ws() -> WebSocket:
    return cast("WebSocket", _StubWS())


@pytest.fixture
def _point_site_manager_at_test_db(monkeypatch, db_session, engine):
    """The WS helper opens its own session via site_manager; in tests that must
    resolve to the test engine, not a real site DB."""
    import contextlib

    from grunt.site.manager import site_manager

    @contextlib.asynccontextmanager
    async def _maker_cm():
        yield db_session

    def _get_session_maker(_site):
        return _maker_cm

    monkeypatch.setattr(site_manager, "get_session_maker", _get_session_maker)
    monkeypatch.setattr(site_manager, "get_engine", lambda _site=None: engine)
    monkeypatch.setattr(site_manager, "get_sites", lambda: ["__pytest__"])


@pytest.fixture
async def _secret(ctx):
    from grunt.api.v1.meta import save_doctype
    from grunt.auth.doctypes.User.user import create_user

    await save_doctype(doctype_data={**SECRET, "__is_new": True})
    owner = await create_user("owner@grunt.example.com", "", "T", "U", None)
    await ctx.save_doc("User", owner.id, {"roles": [{"role_name": "Owner"}]})
    # stranger holds the Owner role too -> may open the list room, but the
    # row-level match keeps them out of someone else's document room.
    stranger = await create_user("stranger@grunt.example.com", "", "T", "U", None)
    await ctx.save_doc("User", stranger.id, {"roles": [{"role_name": "Owner"}]})
    # outsider has no grant at all -> denied even the list room.
    outsider = await create_user("outsider@grunt.example.com", "", "T", "U", None)
    await ctx.save_doc("User", outsider.id, {"roles": []})
    doc = await ctx.new_doc("WsSecret", {"title": "classified"})
    await ctx.set_value("WsSecret", doc["name"], "owner", "owner@grunt.example.com")
    await ctx.db._session().commit()
    return doc["name"]


@pytest.mark.asyncio
async def test_non_reader_cannot_join_document_room(ctx, _secret, _point_site_manager_at_test_db):
    from grunt.api.v1.ws import _ws_user_can_read

    # Owner may read it; a stranger may not.
    assert await _ws_user_can_read(_ws(), "owner@grunt.example.com", "WsSecret", _secret)
    assert not await _ws_user_can_read(_ws(), "stranger@grunt.example.com", "WsSecret", _secret)


@pytest.mark.asyncio
async def test_non_reader_cannot_join_list_room(ctx, _secret, _point_site_manager_at_test_db):
    from grunt.api.v1.ws import _ws_user_can_read

    # doc_id=None -> DocType-level read gate for the list room.
    assert await _ws_user_can_read(_ws(), "owner@grunt.example.com", "WsSecret", None)
    assert not await _ws_user_can_read(_ws(), "outsider@grunt.example.com", "WsSecret", None)


@pytest.mark.asyncio
async def test_virtual_doctype_room_uses_doctype_level_check(ctx, _point_site_manager_at_test_db):
    """A virtual DocType has no table; the document-room check must fall back to
    the DocType-level read grant instead of raising on a missing table and then
    failing closed for everyone."""
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.ws import _ws_user_can_read
    from grunt.auth.doctypes.User.user import create_user

    await save_doctype(
        doctype_data={
            "name": "WsVirtual",
            "label": "Ws Virtual",
            "module": "core",
            "is_virtual": True,
            "fields": [{"fieldname": "title", "label": "T", "fieldtype": "Text"}],
            "permissions": [{"role": "All", "read": True}],
            "__is_new": True,
        }
    )
    user = await create_user("wsv@grunt.example.com", "", "A", "D", None)
    await ctx.save_doc("User", user.id, {"roles": []})
    await ctx.db._session().commit()

    # A read grant exists for "All" -> allowed, without ever touching a table.
    assert await _ws_user_can_read(_ws(), "wsv@grunt.example.com", "WsVirtual", "anything")
