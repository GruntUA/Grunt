"""Tests for the print template renderer."""

from datetime import UTC, date, datetime

from markupsafe import Markup

from grunt.print.filters import JINJA_FILTERS, date_format, datetime_format, striptags
from grunt.print.layout import PrintField, PrintSection, PrintTable
from grunt.print.renderer import (
    _get_jinja_env,
    _render_fallback,
    render_from_string,
    render_standard,
)

# Filter tests


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


# Jinja environment tests


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


# render_from_string tests


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


# render_standard tests


def _field(label="Title", value="Test", fieldname="title", fieldtype="Data", wide=False):
    return PrintField(
        label=label, value=Markup(value), fieldname=fieldname, fieldtype=fieldtype, wide=wide
    )


def _layout(*columns, label="", tab_label=""):
    return [PrintSection(label=label, tab_label=tab_label, columns=list(columns))]


class TestRenderStandard:
    def test_basic_render(self):
        doc = {"name": "DOC-001", "owner": "admin@test.com"}
        html = render_standard("Документ", _layout([_field()]), doc)
        assert "Документ" in html
        assert "DOC-001" in html
        assert "<th>Title</th>" in html
        assert "<td>Test</td>" in html

    def test_title_heads_the_page(self):
        doc = {"name": "DOC-001", "owner": "a@b.com"}
        html = render_standard("Договір", _layout([_field()]), doc, title="Оренда")
        assert "<h1>Оренда</h1>" in html
        assert "Договір · DOC-001" in html

    def test_section_tab_and_columns(self):
        layout = _layout(
            [_field("Left", "L")], [_field("Right", "R")], label="Details", tab_label="Main"
        )
        html = render_standard("Тест", layout, {"name": "D-1"})
        assert '<h2 class="print-tab">Main</h2>' in html
        assert '<div class="print-section-heading">Details</div>' in html
        assert "--cols: 2" in html

    def test_wide_field_under_its_label(self):
        layout = _layout([_field("Notes", "<p>long</p>", wide=True)])
        html = render_standard("Test", layout, {"name": "D-1"})
        assert '<div class="print-wide-label">Notes</div>' in html
        assert "<p>long</p>" in html

    def test_child_table(self):
        table = PrintTable(
            label="Items",
            fieldname="items",
            columns=[("Item", False), ("Qty", True)],
            rows=[[Markup("Bolt"), Markup("3")]],
        )
        html = render_standard("Test", _layout([table]), {"name": "D-1"})
        assert '<div class="print-table-label">Items</div>' in html
        assert '<th class="num">Qty</th>' in html
        assert '<td class="num">3</td>' in html
        assert "<td>Bolt</td>" in html

    def test_labels_are_escaped(self):
        layout = _layout([_field("<img src=x onerror=alert(1)>")], label="<b>S</b>")
        html = render_standard("<script>x</script>", layout, {"name": "<i>n</i>"})
        assert "<img src=x" not in html
        assert "<b>S</b>" not in html
        assert "<script>x</script>" not in html
        assert "<i>n</i>" not in html


# _render_fallback tests


class TestRenderFallback:
    def test_basic(self):
        doc = {"name": "FB-001"}
        html = _render_fallback("MyDoc", _layout([_field("Title", "Fallback Test")]), doc)
        assert "MyDoc" in html
        assert "FB-001" in html
        assert "<th>Title</th><td>Fallback Test</td>" in html
        assert "<!DOCTYPE html>" in html

    def test_tables_left_out(self):
        table = PrintTable(label="Items", fieldname="items", columns=[], rows=[])
        html = _render_fallback("Test", _layout([table, _field("Value", "123")]), {"name": "X"})
        assert "<th>Value</th>" in html
        assert "Items" not in html

    def test_label_html_is_escaped(self):
        layout = _layout([_field("<img src=x onerror=alert(1)>")])
        html = _render_fallback("Test", layout, {"name": "X"})
        assert "<img src=x onerror=alert(1)>" not in html

    def test_doc_name_html_is_escaped(self):
        html = _render_fallback("Test", _layout([_field()]), {"name": "<script>alert(2)</script>"})
        assert "<script>alert(2)</script>" not in html

    def test_doctype_label_html_is_escaped(self):
        html = _render_fallback("<script>alert(3)</script>", _layout([_field()]), {"name": "X"})
        assert "<script>alert(3)</script>" not in html
