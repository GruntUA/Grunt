"""Tests for the Web Form service - validation, field resolution, and submission logic."""

import pytest

from grunt.webform.service import WebFormError, WebFormService


def _resolved_field(fieldname, fieldtype="Text", label=None, required=False):
    """A resolved field dict, the shape `get_form_fields()` returns and
    `_validate_submission()` consumes - target DocType's live properties
    already merged with the WebFormField row's overrides.
    """
    return {
        "fieldname": fieldname,
        "fieldtype": fieldtype,
        "label": label or fieldname.replace("_", " ").title(),
        "required": required,
        "options": None,
        "default": None,
        "validator": None,
    }


class TestValidateSubmission:
    def setup_method(self):
        self.svc = WebFormService()

    def test_valid_submission(self):
        fields = [_resolved_field("title"), _resolved_field("description")]
        result = self.svc._validate_submission(fields, {"title": "Test", "description": "Hello"})
        assert result == {"title": "Test", "description": "Hello"}

    def test_required_field_missing(self):
        fields = [_resolved_field("title", required=True)]
        with pytest.raises(WebFormError, match="обов'язковим"):
            self.svc._validate_submission(fields, {})

    def test_required_field_empty_string(self):
        fields = [_resolved_field("title", required=True)]
        with pytest.raises(WebFormError, match="обов'язковим"):
            self.svc._validate_submission(fields, {"title": ""})

    def test_only_form_fields_pass_through(self):
        # get_form_fields() already limits the list to what the form
        # exposes - a field not in that list simply isn't validated/kept,
        # even if present in the raw POST data.
        fields = [_resolved_field("title")]
        result = self.svc._validate_submission(fields, {"title": "OK", "secret": "HACK"})
        assert "title" in result
        assert "secret" not in result

    def test_skips_layout_rows(self):
        fields = [
            _resolved_field("title"),
            {**_resolved_field("sec"), "fieldtype": "Section"},
            {**_resolved_field("col"), "fieldtype": "Column"},
        ]
        result = self.svc._validate_submission(fields, {"title": "X"})
        assert result == {"title": "X"}

    def test_none_values_excluded(self):
        fields = [_resolved_field("title"), _resolved_field("notes")]
        result = self.svc._validate_submission(fields, {"title": "X"})
        assert "notes" not in result

    def test_multiple_required_errors(self):
        fields = [
            _resolved_field("first_name", required=True),
            _resolved_field("last_name", required=True),
        ]
        with pytest.raises(WebFormError) as exc_info:
            self.svc._validate_submission(fields, {})
        assert "First Name" in str(exc_info.value)
        assert "Last Name" in str(exc_info.value)

    def test_optional_field_accepted(self):
        fields = [_resolved_field("name", required=True), _resolved_field("notes")]
        result = self.svc._validate_submission(fields, {"name": "Test"})
        assert result == {"name": "Test"}


class TestWebFormError:
    def test_is_exception(self):
        err = WebFormError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"
