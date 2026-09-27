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
