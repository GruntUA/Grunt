"""Tests for the print template renderer."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

from grunt.print.filters import JINJA_FILTERS, date_format, datetime_format, striptags
from grunt.print.renderer import (
    _get_jinja_env,
    _render_fallback,
    render_from_string,
    render_standard,
)

# ── Filter tests ─────────────────────────────────────────────────────────


class TestDateFormatFilter:
    def test_date_object(self):
        assert date_format(date(2025, 3, 15)) == "15.03.2025"

    def test_datetime_object(self):
        assert date_format(datetime(2025, 3, 15, 10, 30)) == "15.03.2025"

    def test_iso_string(self):
        assert date_format("2025-03-15") == "15.03.2025"

    def test_custom_format(self):
        assert date_format(date(2025, 3, 15), "%Y/%m/%d") == "2025/03/15"

    def test_none(self):
        assert date_format(None) == ""

    def test_invalid_string(self):
        assert date_format("not-a-date") == "not-a-date"


class TestDatetimeFormatFilter:
    def test_datetime_object(self):
        assert datetime_format(datetime(2025, 3, 15, 10, 30)) == "15.03.2025 10:30"

    def test_iso_string(self):
        result = datetime_format("2025-03-15T10:30:00")
        assert result == "15.03.2025 10:30"

    def test_none(self):
        assert datetime_format(None) == ""

    def test_invalid_string(self):
        assert datetime_format("bad") == "bad"

    def test_custom_format(self):
        assert datetime_format(datetime(2025, 3, 15, 10, 30), "%H:%M") == "10:30"


class TestStriptagsFilter:
    def test_basic(self):
        assert striptags("<b>hello</b>") == "hello"

    def test_nested(self):
        assert striptags("<div><p>text</p></div>") == "text"

    def test_none(self):
        assert striptags(None) == ""

    def test_empty(self):
        assert striptags("") == ""


class TestJinjaFiltersDict:
    def test_all_filters_registered(self):
        assert "date_format" in JINJA_FILTERS
        assert "datetime_format" in JINJA_FILTERS
        assert "striptags" in JINJA_FILTERS


# ── Jinja environment tests ─────────────────────────────────────────────


class TestJinjaEnv:
    def test_env_has_filters(self):
        env = _get_jinja_env()
        assert "date_format" in env.filters
        assert "datetime_format" in env.filters
        assert "striptags" in env.filters

    def test_env_has_autoescape(self):
        env = _get_jinja_env()
        # HTML autoescape is enabled
        assert env.autoescape is True or callable(env.autoescape)


# ── render_from_string tests ─────────────────────────────────────────────


class TestRenderFromString:
    def test_simple_template(self):
        html = render_from_string("<p>{{ doc.name }}</p>", {"name": "DOC-001"})
        assert "DOC-001" in html

    def test_with_extra_vars(self):
        html = render_from_string(
            "<p>{{ doc.name }} — {{ doctype_label }}</p>",
            {"name": "DOC-001"},
            doctype_label="Договір",
        )
        assert "Договір" in html
        assert "DOC-001" in html

    def test_filters_available(self):
        html = render_from_string(
            "{{ doc.dt | date_format }}",
            {"dt": "2025-03-15"},
        )
        assert "15.03.2025" in html

    def test_now_variable(self):
        html = render_from_string("{{ now.year }}", {})
        assert str(datetime.now(UTC).year) in html


# ── render_standard tests ────────────────────────────────────────────────


def _make_field(fieldtype="Text", fieldname="title", label="Title", hidden=False):
    return SimpleNamespace(fieldtype=fieldtype, fieldname=fieldname, label=label, hidden=hidden)


class TestRenderStandard:
    def test_basic_render(self):
        fields = [_make_field()]
        doc = {"name": "DOC-001", "title": "Test", "owner": "admin@test.com"}
        html = render_standard("Документ", fields, doc)
        assert "Документ" in html
        assert "DOC-001" in html
        assert "Test" in html

    def test_section_heading(self):
        fields = [
            _make_field(fieldtype="Section", fieldname="sec", label="Details"),
            _make_field(fieldname="title", label="Title"),
        ]
        doc = {"name": "DOC-001", "title": "Hello", "owner": "admin@test.com"}
        html = render_standard("Тест", fields, doc)
        assert "Details" in html
        assert "Hello" in html

    def test_hidden_field_excluded(self):
        fields = [
            _make_field(fieldname="visible", label="Visible"),
            _make_field(fieldname="secret", label="Secret", hidden=True),
        ]
        doc = {"name": "D-1", "visible": "yes", "secret": "no", "owner": "a@b.com"}
        html = render_standard("Test", fields, doc)
        assert "Visible" in html
        assert "Secret" not in html

    def test_check_field(self):
        fields = [_make_field(fieldtype="Check", fieldname="active", label="Active")]
        doc = {"name": "D-1", "active": True, "owner": "a@b.com"}
        html = render_standard("Test", fields, doc)
        assert "check-true" in html

    def test_structural_fields_not_as_rows(self):
        """Column, Tab, Table fieldtypes should not produce data rows."""
        fields = [
            _make_field(fieldtype="Column", fieldname="col", label="Col"),
            _make_field(fieldtype="Tab", fieldname="tab", label="Tab"),
            _make_field(fieldtype="Table", fieldname="tbl", label="Tbl"),
        ]
        doc = {"name": "D-1", "owner": "a@b.com"}
        html = render_standard("Test", fields, doc)
        # These should not appear as <th> cells
        assert "<th>Col</th>" not in html
        assert "<th>Tab</th>" not in html
        assert "<th>Tbl</th>" not in html

    def test_date_field_uses_filter(self):
        fields = [_make_field(fieldtype="Date", fieldname="dt", label="Date")]
        doc = {"name": "D-1", "dt": "2025-03-15", "owner": "a@b.com"}
        html = render_standard("Test", fields, doc)
        assert "15.03.2025" in html


# ── _render_fallback tests ───────────────────────────────────────────────


class TestRenderFallback:
    def test_basic(self):
        fields = [_make_field(fieldname="title", label="Title")]
        doc = {"name": "FB-001", "title": "Fallback Test"}
        html = _render_fallback("MyDoc", fields, doc)
        assert "MyDoc" in html
        assert "FB-001" in html
        assert "Fallback Test" in html
        assert "<!DOCTYPE html>" in html

    def test_skips_structural(self):
        fields = [
            _make_field(fieldtype="Section", fieldname="s", label="S"),
            _make_field(fieldtype="Column", fieldname="c", label="C"),
            _make_field(fieldtype="Tab", fieldname="t", label="T"),
            _make_field(fieldtype="Table", fieldname="tb", label="TB"),
            _make_field(fieldname="val", label="Value"),
        ]
        doc = {"name": "X", "val": "123"}
        html = _render_fallback("Test", fields, doc)
        assert "<th>Value</th>" in html
        assert "<th>S</th>" not in html

    def test_skips_hidden(self):
        fields = [_make_field(fieldname="h", label="Hidden", hidden=True)]
        doc = {"name": "X", "h": "secret"}
        html = _render_fallback("Test", fields, doc)
        assert "Hidden" not in html

    def test_none_value_rendered_as_empty(self):
        fields = [_make_field(fieldname="f", label="F")]
        doc = {"name": "X"}
        html = _render_fallback("Test", fields, doc)
        assert "<td></td>" in html
