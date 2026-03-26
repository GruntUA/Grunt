"""Tests for the Naming Series module."""

from datetime import datetime, timezone

from grunt.core.naming.patterns import (
    build_prefix,
    format_name,
    has_counter,
    parse_pattern,
    resolve_simple,
)


class TestParsePattern:
    def test_simple_prefix_with_counter(self):
        parts = parse_pattern("ACC-.####")
        assert len(parts) == 2
        assert parts[0] == "ACC-"
        assert parts[1] == ("counter", 4)

    def test_year_and_counter(self):
        parts = parse_pattern("INV-.YYYY.-.####")
        assert parts == ["INV-", ("YYYY", 0), "-", ("counter", 4)]

    def test_full_date_and_counter(self):
        parts = parse_pattern("CONTR-.YYYY.-.MM.-.DD.-.#####")
        assert ("YYYY", 0) in parts
        assert ("MM", 0) in parts
        assert ("DD", 0) in parts
        assert ("counter", 5) in parts

    def test_no_counter(self):
        parts = parse_pattern("REF-.YYYY.-.MM")
        assert not has_counter(parts)

    def test_two_digit_year(self):
        parts = parse_pattern("X-.YY.-.###")
        assert ("YY", 0) in parts
        assert ("counter", 3) in parts


class TestFormatName:
    def test_format_with_counter(self):
        parts = parse_pattern("INV-.YYYY.-.####")
        now = datetime(2026, 3, 26, tzinfo=timezone.utc)
        name = format_name(parts, counter=42, now=now)
        assert name == "INV-2026-0042"

    def test_format_five_digit_counter(self):
        parts = parse_pattern("ACC-.#####")
        name = format_name(parts, counter=7)
        assert name == "ACC-00007"

    def test_format_with_month(self):
        parts = parse_pattern("DOC-.YYYY.-.MM.-.###")
        now = datetime(2026, 1, 5, tzinfo=timezone.utc)
        name = format_name(parts, counter=1, now=now)
        assert name == "DOC-2026-01-001"


class TestBuildPrefix:
    def test_prefix_stops_at_counter(self):
        parts = parse_pattern("INV-.YYYY.-.####")
        now = datetime(2026, 3, 26, tzinfo=timezone.utc)
        prefix = build_prefix(parts, now=now)
        assert prefix == "INV-2026-"

    def test_prefix_with_month(self):
        parts = parse_pattern("X-.YYYY.-.MM.-.###")
        now = datetime(2026, 7, 15, tzinfo=timezone.utc)
        prefix = build_prefix(parts, now=now)
        assert prefix == "X-2026-07-"

    def test_prefix_no_date(self):
        parts = parse_pattern("ACC-.####")
        prefix = build_prefix(parts)
        assert prefix == "ACC-"


class TestResolveSimple:
    def test_field_pattern(self):
        assert resolve_simple("field:title", {"title": "Hello"}) == "Hello"

    def test_field_missing(self):
        assert resolve_simple("field:title", {}) is None

    def test_hash_pattern(self):
        result = resolve_simple("hash", {})
        assert result is not None
        assert len(result) == 10

    def test_prompt_pattern(self):
        assert resolve_simple("prompt", {"name": "CUSTOM"}) == "CUSTOM"

    def test_prompt_missing(self):
        assert resolve_simple("prompt", {}) is None

    def test_counter_pattern_returns_none(self):
        assert resolve_simple("INV-.YYYY.-.####", {}) is None


class TestHasCounter:
    def test_with_counter(self):
        assert has_counter(parse_pattern("INV-.####")) is True

    def test_without_counter(self):
        assert has_counter(parse_pattern("REF-.YYYY")) is False
