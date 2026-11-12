"""Tests for the Notification module."""

from grunt.notification import rules
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


class TestRender:
    async def test_jinja_template(self):
        ctx = {"doctype": "Invoice", "event": "after_save", "doc": rules._Doc({"name": "INV-001"})}
        result = await rules.render("{{ doctype }}: {{ doc.name }} was {{ event }}", ctx)
        assert result == "Invoice: INV-001 was after_save"

    async def test_plain_text_is_kept(self):
        assert await rules.render("Status changed", {}) == "Status changed"

    async def test_missing_variable_renders_empty(self):
        assert await rules.render("[{{ doc.nothing }}]", {"doc": rules._Doc({})}) == "[]"

    async def test_broken_template_returns_it_as_is(self):
        assert await rules.render("{{ oops", {}) == "{{ oops"

    async def test_sandbox_blocks_dunder(self):
        out = await rules.render("{{ doc.__class__.__mro__ }}", {"doc": rules._Doc({})})
        assert "object" not in out

    async def test_check_template(self):
        assert await rules.check_template("{{ doc.name }}") is None
        assert await rules.check_template("{% if %}")


class TestEvalCondition:
    def test_true_condition(self):
        assert rules.eval_condition("doc.status == 'Active'", {"status": "Active"}, "u@x")

    def test_get_style_still_works(self):
        assert rules.eval_condition("doc.get('status') == 'Active'", {"status": "Active"}, "u")

    def test_false_condition(self):
        assert not rules.eval_condition("doc.status == 'Active'", {"status": "Draft"}, "u@x")

    def test_empty_condition_is_true(self):
        assert rules.eval_condition("", {}, "u@x")

    def test_invalid_condition_is_false(self):
        """A typo must not notify everybody - the form validates the syntax on save."""
        assert not rules.eval_condition("invalid python {{{{", {}, "u@x")
