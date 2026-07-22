"""Tests for dashboard module — aggregation helpers and config validation."""

from datetime import UTC, datetime, timedelta

from grunt.api.v1.dashboard import _TIMESPAN_DAYS, _resolve_relative_date, _widget_filters


class TestTimespanConfig:
    def test_all_timespans_defined(self):
        expected = {
            "last_week",
            "last_month",
            "last_quarter",
            "last_year",
            "all_time",
            "7d",
            "30d",
            "90d",
            "365d",
        }
        assert set(_TIMESPAN_DAYS.keys()) == expected

    def test_last_week_days(self):
        assert _TIMESPAN_DAYS["last_week"] == 7

    def test_last_month_days(self):
        assert _TIMESPAN_DAYS["last_month"] == 30

    def test_last_quarter_days(self):
        assert _TIMESPAN_DAYS["last_quarter"] == 90

    def test_last_year_days(self):
        assert _TIMESPAN_DAYS["last_year"] == 365

    def test_all_time_no_filter(self):
        assert _TIMESPAN_DAYS["all_time"] == 0


class TestWidgetFilters:
    def test_missing_filters(self):
        assert _widget_filters({}) == {}

    def test_empty_string(self):
        assert _widget_filters({"filters": ""}) == {}

    def test_none(self):
        assert _widget_filters({"filters": None}) == {}

    def test_dict_passthrough(self):
        assert _widget_filters({"filters": {"status": "Виконано"}}) == {"status": "Виконано"}

    def test_dict_is_copied(self):
        original = {"status": "Виконано"}
        result = _widget_filters({"filters": original})
        result["status"] = "Архів"
        assert original == {"status": "Виконано"}

    def test_json_string_decoded(self):
        assert _widget_filters({"filters": '{"status": "На виконанні"}'}) == {
            "status": "На виконанні"
        }

    def test_operator_suffix_preserved(self):
        assert _widget_filters({"filters": '{"due_date__lt": "2026-01-01"}'}) == {
            "due_date__lt": "2026-01-01"
        }

    def test_malformed_json_ignored(self):
        assert _widget_filters({"filters": "{not json"}) == {}

    def test_non_object_json_ignored(self):
        assert _widget_filters({"filters": "[1, 2, 3]"}) == {}

    def test_relative_date_resolved_in_filters(self):
        today = datetime.now(UTC).date().isoformat()
        assert _widget_filters({"filters": '{"due_date__lt": "@today"}'}) == {"due_date__lt": today}


class TestRelativeDates:
    def test_today(self):
        assert _resolve_relative_date("@today") == datetime.now(UTC).date().isoformat()

    def test_today_minus_days(self):
        expected = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
        assert _resolve_relative_date("@today-7d") == expected

    def test_today_plus_days(self):
        expected = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
        assert _resolve_relative_date("@today+30d") == expected

    def test_weeks_months_years(self):
        for token, days in (("@today-2w", 14), ("@today-1m", 30), ("@today-1y", 365)):
            expected = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
            assert _resolve_relative_date(token) == expected, token

    def test_whitespace_tolerated(self):
        expected = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
        assert _resolve_relative_date(" @today - 7d ") == expected

    def test_case_insensitive(self):
        assert _resolve_relative_date("@TODAY") == datetime.now(UTC).date().isoformat()

    def test_now_returns_timestamp(self):
        result = _resolve_relative_date("@now")
        assert "T" in result

    def test_plain_date_untouched(self):
        assert _resolve_relative_date("2026-01-01") == "2026-01-01"

    def test_plain_string_untouched(self):
        assert _resolve_relative_date("На виконанні") == "На виконанні"

    def test_non_string_untouched(self):
        assert _resolve_relative_date(42) == 42
        assert _resolve_relative_date(None) is None
        assert _resolve_relative_date(["a"]) == ["a"]

    def test_unknown_token_untouched(self):
        assert _resolve_relative_date("@tomorrow") == "@tomorrow"

    def test_bad_unit_untouched(self):
        assert _resolve_relative_date("@today-5x") == "@today-5x"
