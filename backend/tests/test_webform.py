"""Tests for the Web Form service — validation and submission logic."""

import pytest
from types import SimpleNamespace

from grunt.core.webform.service import WebFormService, WebFormError


def _make_field(fieldname, fieldtype="Text", label=None, required=False, options=None, default=None):
    return SimpleNamespace(
        fieldname=fieldname,
        fieldtype=fieldtype,
        label=label or fieldname.replace("_", " ").title(),
        required=required,
        options=options,
        default=default,
    )


class TestValidateSubmission:
    def setup_method(self):
        self.svc = WebFormService()

    def _make_dt(self, fields):
        return SimpleNamespace(fields=fields)

    def test_valid_submission(self):
        dt = self._make_dt([_make_field("title"), _make_field("description")])
        result = self.svc._validate_submission(dt, {"title": "Test", "description": "Hello"}, None)
        assert result == {"title": "Test", "description": "Hello"}

    def test_required_field_missing(self):
        dt = self._make_dt([_make_field("title", required=True)])
        with pytest.raises(WebFormError, match="обов'язковим"):
            self.svc._validate_submission(dt, {}, None)

    def test_required_field_empty_string(self):
        dt = self._make_dt([_make_field("title", required=True)])
        with pytest.raises(WebFormError, match="обов'язковим"):
            self.svc._validate_submission(dt, {"title": ""}, None)

    def test_allowed_fields_filter(self):
        dt = self._make_dt([
            _make_field("title"),
            _make_field("secret"),
        ])
        result = self.svc._validate_submission(
            dt,
            {"title": "OK", "secret": "HACK"},
            allowed_fields={"title"},
        )
        assert "title" in result
        assert "secret" not in result

    def test_skips_non_physical_fields(self):
        dt = self._make_dt([
            _make_field("title"),
            _make_field("sec", fieldtype="Section"),
            _make_field("col", fieldtype="Column"),
        ])
        result = self.svc._validate_submission(dt, {"title": "X"}, None)
        assert result == {"title": "X"}

    def test_none_values_excluded(self):
        dt = self._make_dt([
            _make_field("title"),
            _make_field("notes"),
        ])
        result = self.svc._validate_submission(dt, {"title": "X"}, None)
        assert "notes" not in result

    def test_multiple_required_errors(self):
        dt = self._make_dt([
            _make_field("first_name", required=True),
            _make_field("last_name", required=True),
        ])
        with pytest.raises(WebFormError) as exc_info:
            self.svc._validate_submission(dt, {}, None)
        assert "First Name" in str(exc_info.value)
        assert "Last Name" in str(exc_info.value)

    def test_optional_field_accepted(self):
        dt = self._make_dt([
            _make_field("name", required=True),
            _make_field("notes"),
        ])
        result = self.svc._validate_submission(dt, {"name": "Test"}, None)
        assert result == {"name": "Test"}

    def test_check_field_skipped_in_non_physical(self):
        """Table, Tab, Column are non-physical and should be skipped."""
        dt = self._make_dt([
            _make_field("items", fieldtype="Table"),
            _make_field("tab1", fieldtype="Tab"),
            _make_field("title"),
        ])
        result = self.svc._validate_submission(dt, {"title": "X", "items": "ignored"}, None)
        assert result == {"title": "X"}


class TestWebFormError:
    def test_is_exception(self):
        err = WebFormError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"
