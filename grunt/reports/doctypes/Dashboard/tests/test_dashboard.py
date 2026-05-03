"""Tests for dashboard module — aggregation helpers and config validation."""

from grunt.api.v1.dashboard import _TIMESPAN_DAYS


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
