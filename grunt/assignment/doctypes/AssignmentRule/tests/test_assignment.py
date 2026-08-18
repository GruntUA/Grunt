"""Tests for the Assignment Rules system (migrated to whitelisted methods)."""

from __future__ import annotations

import pytest

from grunt.assignment import AssignmentService


class TestAssignmentFilters:
    """Test filter matching logic (Unit tests, no change needed)."""

    @pytest.fixture(autouse=True)
    def setup_service(self):
        self.service = AssignmentService()

    @pytest.mark.asyncio
    async def test_simple_match(self):
        doc = {"id": "1", "name": "DOC-001", "status": "Draft", "title": "Test"}
        filters = {"status": "Draft"}
        assert self.service._match_filters(doc, filters) is True

    @pytest.mark.asyncio
    async def test_simple_no_match(self):
        doc = {"status": "Submitted"}
        filters = {"status": "Draft"}
        assert self.service._match_filters(doc, filters) is False

    @pytest.mark.asyncio
    async def test_operator_greater_than(self):
        doc = {"amount": 1500}
        filters = {"amount": {">": 1000}}
        assert self.service._match_filters(doc, filters) is True

    @pytest.mark.asyncio
    async def test_operator_in(self):
        doc = {"status": "Draft"}
        filters = {"status": {"in": ["Draft", "Pending"]}}
        assert self.service._match_filters(doc, filters) is True


class TestAssignmentIntegration:
    """Integration tests with async operations."""

    @pytest.mark.asyncio
    async def test_evaluate_and_assign_no_rules(self, ctx):
        """When no rules exist, nothing happens."""
        from grunt.assignment import assignment_service

        await assignment_service.evaluate_and_assign(
            doctype="Invoice",
            doc={"id": "1", "status": "Draft"},
        )


class TestAssignmentAPI:
    """Test assignment endpoints logic (Migrated)."""

    @pytest.mark.asyncio
    async def test_test_assignment_rule_api(self, ctx):
        """Test the assignment rule test logic directly."""
        from grunt.assignment.doctypes.AssignmentRule.assignment_rule import test_rule

        # 1. Create a rule via documents API
        rule_data = {
            "name": "Test Rule API",
            "doctype_target": "Invoice",
            "filters": '{"status": "Draft"}',
            "assign_to_user": "admin@grunt.local",
            "enabled": True,
        }
        rule = await ctx.new_doc("AssignmentRule", rule_data)
        await ctx.db._session().commit()

        # 2. Test the rule
        test_doc = {"status": "Draft", "amount": 100}
        data = await test_rule(rule_id=rule["name"], test_doc=test_doc)

        assert data["matched"] is True
        assert data["will_assign_to"] == ["admin@grunt.local"]

    async def test_list_assignment_logs_api(self, ctx):
        """Test the assignment log listing logic directly."""
        import datetime

        from grunt.assignment.doctypes.AssignmentLog.assignment_log import list_logs

        log_doc = {
            "doctype_affected": "Invoice",
            "document_id": "INV-TEST",
            "assigned_to": "admin@grunt.example.com",
            "assignment_method": "user",
            "status": "Success",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        await ctx.new_doc("AssignmentLog", log_doc)
        await ctx.db._session().commit()

        data = await list_logs(doctype="Invoice")

        assert data["count"] >= 1
        assert any(log["document_id"] == "INV-TEST" for log in data["data"])
