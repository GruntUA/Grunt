"""A sidebar item's count_filters reach the client together with its count key."""

from __future__ import annotations

import pytest

from grunt.site.doctypes.AppMenu.app_menu import count_key, parse_count_filters


def test_count_key_matches_filters() -> None:
    assert count_key("WebsiteMenuItem", {}) == "WebsiteMenuItem"
    assert count_key("WebsiteMenuItem", {"menu": "MLT_Portal"}) == "WebsiteMenuItem_mlt_portal"
    assert parse_count_filters({"count_filters": '{"menu": "mlt_portal"}'}) == {
        "menu": "mlt_portal"
    }
    assert parse_count_filters({"count_filters": "not json"}) == {}


@pytest.mark.asyncio
async def test_workspace_items_carry_count_filters_and_key(ctx) -> None:
    from grunt.api.v1.workspace import _workspace_to_dict

    data = await _workspace_to_dict(
        {
            "name": "demo",
            "label": "Demo",
            "sidebar_items": [
                {
                    "type": "DocType",
                    "label": "Menu",
                    "link_to": "WebsiteMenuItem",
                    "show_count": 1,
                    "count_filters": '{"menu": "mlt_portal"}',
                },
                {"type": "DocType", "label": "All", "link_to": "WebsiteMenuItem"},
            ],
        }
    )
    filtered, plain = data["items"]
    assert filtered["count_filters"] == '{"menu": "mlt_portal"}'
    assert filtered["count_key"] == "WebsiteMenuItem_mlt_portal"
    assert plain["count_key"] == "WebsiteMenuItem"


@pytest.mark.asyncio
async def test_count_of_virtual_doctype_uses_its_controller(ctx) -> None:
    """A virtual DocType's sidebar badge comes from its controller, not from
    the table count path (which crashed on ``list_filter_extra``)."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document.collection import count_documents
    from grunt.scripting.doctypes.Hook.hook import Hook

    session = ctx.get_session()
    expected = await Hook.get_count("Hook", session=session, user=SYSTEM_USER)
    assert await count_documents(session, "Hook", SYSTEM_USER) == expected


@pytest.mark.asyncio
async def test_count_of_doctype_comes_from_its_table(ctx) -> None:
    """``DocType`` reads and writes single documents through the registry,
    but its definitions are rows of its own table - the count reads that table."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.document.collection import count_documents
    from grunt.metadata import store

    session = ctx.get_session()
    assert await count_documents(session, "DocType", SYSTEM_USER) == len(await store.names(session))
