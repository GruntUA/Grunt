"""Date/Datetime defaults ``"Today"`` / ``"Now"`` on the server.

The form resolved them, the server coerced the token itself - ``new_doc``
without a value for such a field (a sync, a script, a fixture) failed with
``ValueError: Invalid isoformat string: 'Today'``.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from grunt.config import settings
from grunt.document.relations import apply_field_values
from grunt.metadata.field import DocField


def _today() -> date:
    return datetime.now(ZoneInfo(settings.default_timezone)).date()


def test_today_on_a_date_field_is_the_site_date():
    for token in ("Today", "today", " Today "):
        assert DocField(fieldname="d", fieldtype="Date", default=token).default_value() == _today()


def test_now_on_a_datetime_field_is_this_moment():
    for token in ("Now", "Today"):
        value = DocField(fieldname="t", fieldtype="Datetime", default=token).default_value()
        assert isinstance(value, datetime) and value.tzinfo is not None
        assert abs(value - datetime.now(UTC)) < timedelta(minutes=1)


def test_static_defaults_are_coerced_as_before():
    assert DocField(fieldname="d", fieldtype="Date", default="2026-01-02").default_value() == date(
        2026, 1, 2
    )
    assert DocField(fieldname="n", fieldtype="Int", default="5").default_value() == 5
    assert DocField(fieldname="s", fieldtype="Data", default="Today").default_value() == "Today"
    assert DocField(fieldname="x", fieldtype="Data").default_value() is None


def test_insert_row_gets_the_resolved_default_unless_given():
    fields = [DocField(fieldname="reg_date", fieldtype="Date", default="Today")]
    row: dict = {}
    apply_field_values(fields, {}, row)
    assert row == {"reg_date": _today()}

    row = {}
    apply_field_values(fields, {"reg_date": "2026-11-24"}, row)
    assert row == {"reg_date": date(2026, 11, 24)}
