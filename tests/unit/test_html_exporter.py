"""HtmlExporter - list view export rendered from templates/list_export.html."""

from unittest.mock import AsyncMock, patch

import pytest

from grunt.io import ListExportContext
from grunt.io.exporters.html import HtmlExporter, _Formatter
from grunt.metadata.field import DocField


def _field(fieldname: str, fieldtype: str = "Data", options: str | None = None) -> DocField:
    return DocField(
        fieldname=fieldname, label=fieldname.title(), fieldtype=fieldtype, options=options
    )


async def _render(rows, fields, ctx=None, settings=None) -> str:
    with (
        patch("grunt.io.exporters.html.grunt.get_meta", AsyncMock(return_value=None)),
        patch(
            "grunt.io.exporters.html.get_system_settings",
            AsyncMock(return_value=settings or {"date_format": "dd.mm.yyyy", "timezone": "UTC"}),
        ),
    ):
        exporter = HtmlExporter()
        ctx = ctx or ListExportContext(total=len(rows))
        return (await exporter.export_list("Task", rows, fields, ctx)).decode()


class TestFormatter:
    fmt = _Formatter("dd.mm.yyyy", None, "uk")

    def test_number_uses_locale_separators(self):
        assert self.fmt.number(1234567.5) == "1 234 567,5"
        assert _Formatter("dd.mm.yyyy", None, "en").number(1234.25) == "1,234.25"

    def test_dates_follow_date_format(self):
        assert self.fmt(("2026-10-22"), _field("d", "Date")) == "22.10.2026"
        iso = _Formatter("yyyy-mm-dd", None, "uk")
        assert iso("2026-10-22 09:05:00", _field("d", "Datetime")) == "2026-10-22 09:05"

    def test_duration_and_bytes(self):
        assert "1" in self.fmt(3_660, _field("t", "Duration"))
        assert self.fmt(2048, _field("size", "Int", options="Bytes")).startswith("2")

    def test_empty(self):
        assert self.fmt(None, _field("x")) == "—"


class TestHtmlExporter:
    @pytest.mark.asyncio
    async def test_values_are_escaped(self):
        html = await _render([{"title": "<script>alert(1)</script>"}], [_field("title")])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    @pytest.mark.asyncio
    async def test_color_cannot_break_out_of_style(self):
        html = await _render([{"c": 'red" onmouseover="x'}], [_field("c", "Color")])
        assert 'onmouseover="x' not in html

    @pytest.mark.asyncio
    async def test_grouping_and_header(self):
        rows = [
            {"title": "a", "status": "Open"},
            {"title": "b", "status": "Closed"},
            {"title": "c", "status": "Open"},
        ]
        ctx = ListExportContext(total=3, group_by="status", filter_summary="Title like x")
        html = await _render(rows, [_field("title"), _field("status", "Select")], ctx)
        assert html.count('class="group-header"') == 2
        assert "Title like x" in html
        assert '<span class="group-count">2</span>' in html

    @pytest.mark.asyncio
    async def test_check_and_rating(self):
        html = await _render(
            [{"done": 1, "stars": 3}], [_field("done", "Check"), _field("stars", "Rating")]
        )
        assert "check-yes" in html
        assert "★★★" in html and "☆☆" in html
