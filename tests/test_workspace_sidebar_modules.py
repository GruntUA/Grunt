"""Sidebar sections reach the client with icons and the resolved sidebar mode (modules/sections)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from grunt.api.v1.workspace import _sections, _sidebar_mode


def _item(section: str, icon: str = "", type_: str = "DocType") -> dict:
    return {"section": section, "icon": icon, "type": type_}


def test_section_icon_from_table_else_first_item() -> None:
    ws = {"sections": [{"section": "Users", "icon": "shield-check"}]}
    items = [
        _item("Users", "user"),
        _item("Mail", "mail"),
        _item("Users", "key"),
        _item("Mail", "inbox"),
        _item("", "home"),
        _item("Spacer", type_="Divider"),
    ]
    assert _sections(ws, items) == [
        {"section": "Users", "icon": "shield-check"},
        {"section": "Mail", "icon": "mail"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("style", "count", "mode"),
    [
        ("Auto", 5, "sections"),
        ("Auto", 6, "modules"),
        (None, 6, "modules"),
        ("Sections", 20, "sections"),
        ("Modules", 1, "modules"),
    ],
)
async def test_sidebar_mode(style: str | None, count: int, mode: str) -> None:
    sections = [{"section": f"S{i}", "icon": ""} for i in range(count)]
    with patch("grunt.api.v1.workspace.get_setting", AsyncMock(return_value=6)):
        assert await _sidebar_mode({"sidebar_style": style}, sections) == mode
