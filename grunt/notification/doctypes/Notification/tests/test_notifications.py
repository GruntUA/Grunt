"""Tests for the Notification module."""

from grunt.notification.service import NotificationService


class TestResolveRecipients:
    def setup_method(self):
        self.svc = NotificationService()

    def test_owner_recipient(self):
        doc = {"owner": "john@example.com"}
        recipients, role_parts = self.svc._resolve_recipients("owner", doc, "admin@example.com")
        assert recipients == ["john@example.com"]
        assert role_parts == []

    def test_owner_not_trigger_user(self):
        """Owner should not be notified if they triggered the event."""
        doc = {"owner": "admin@example.com"}
        recipients, _ = self.svc._resolve_recipients("owner", doc, "admin@example.com")
        assert recipients == []

    def test_literal_email(self):
        doc = {}
        recipients, _ = self.svc._resolve_recipients(
            "manager@example.com", doc, "admin@example.com"
        )
        assert recipients == ["manager@example.com"]

    def test_field_reference(self):
        doc = {"assigned_to": "worker@example.com"}
        recipients, _ = self.svc._resolve_recipients(
            "{field:assigned_to}", doc, "admin@example.com"
        )
        assert recipients == ["worker@example.com"]

    def test_multiple_recipients(self):
        doc = {"owner": "john@example.com"}
        recipients, _ = self.svc._resolve_recipients(
            "owner, manager@example.com", doc, "admin@example.com"
        )
        assert set(recipients) == {"john@example.com", "manager@example.com"}

    def test_role_recipient_deferred_for_async_lookup(self):
        """role:X parts aren't resolved here - they come back as role_parts for
        the caller to look up asynchronously (see _resolve_role_recipients)."""
        doc = {}
        recipients, role_parts = self.svc._resolve_recipients(
            "role:Manager, owner", doc, "admin@example.com"
        )
        assert recipients == []
        assert role_parts == ["Manager"]

    def test_empty_recipients(self):
        doc = {}
        recipients, role_parts = self.svc._resolve_recipients("", doc, "admin@example.com")
        assert recipients == []
        assert role_parts == []


class TestFormatTemplate:
    def setup_method(self):
        self.svc = NotificationService()

    def test_basic_template(self):
        result = self.svc._format_template(
            "{doctype}: {name} was {event}",
            "Invoice",
            {"name": "INV-001", "id": "abc"},
            "after_save",
        )
        assert result == "Invoice: INV-001 was after_save"

    def test_doc_field_in_template(self):
        result = self.svc._format_template(
            "Status changed to {status}",
            "Order",
            {"name": "ORD-1", "id": "x", "status": "Active"},
            "after_save",
        )
        assert result == "Status changed to Active"

    def test_missing_key_returns_template(self):
        result = self.svc._format_template(
            "{unknown_key}",
            "X",
            {"name": "Y", "id": "z"},
            "after_save",
        )
        # Should not crash, returns original template
        assert isinstance(result, str)


class TestEvalCondition:
    def setup_method(self):
        self.svc = NotificationService()

    def test_true_condition(self):
        assert (
            self.svc._eval_condition(
                "doc.get('status') == 'Active'",
                {"status": "Active"},
                "user@example.com",
            )
            is True
        )

    def test_false_condition(self):
        assert (
            self.svc._eval_condition(
                "doc.get('status') == 'Active'",
                {"status": "Draft"},
                "user@example.com",
            )
            is False
        )

    def test_invalid_condition_returns_true(self):
        """Invalid conditions should not block notifications."""
        assert (
            self.svc._eval_condition(
                "invalid python {{{{",
                {},
                "user@example.com",
            )
            is True
        )
