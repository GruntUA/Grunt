"""Tests for dashboard module — aggregation helpers and config validation."""

from grunt.api.v1.dashboard import _TIMESPAN_DAYS, _widget_filters


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
