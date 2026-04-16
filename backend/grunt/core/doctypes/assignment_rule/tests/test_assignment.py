"""Tests for the Assignment Rules system (migrated to whitelisted methods)."""

from __future__ import annotations
import pytest
from grunt.core.assignment import AssignmentService

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
    async def test_evaluate_and_assign_no_rules(self, ctx, db_session):
        """When no rules exist, nothing happens."""
        from grunt.core.assignment import assignment_service

        await assignment_service.evaluate_and_assign(
            doctype="Invoice",
            doc={"id": "1", "status": "Draft"},
            session=db_session,
        )


class TestAssignmentAPI:
    """Test assignment endpoints logic (Migrated)."""

    @pytest.mark.asyncio
    async def test_test_assignment_rule_api(self, client, auth_headers):
        """Test the grunt.api.v1.assignment.test_rule method."""
        # 1. Create a rule via documents API
        rule_data = {
            "name": "Test Rule API",
            "doctype_target": "Invoice",
            "filters": '{"status": "Draft"}',
            "assign_to_user": "admin@grunt.local",
            "enabled": True,
        }
        resp = await client.post(
            "/api/v1/method/grunt.api.v1.documents.new_doc", 
            headers=auth_headers, 
            json={"doctype": "AssignmentRule", "data": rule_data}
        )
        assert resp.status_code == 200, resp.text
        rule_id = resp.json()["data"]["id"]

        # 2. Test the rule
        test_doc = {"status": "Draft", "amount": 100}
        resp = await client.post(
            "/api/v1/method/grunt.core.doctypes.assignment_rule.assignment_rule.test_rule",
            headers=auth_headers,
            json={"rule_id": rule_id, "test_doc": test_doc},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["matched"] is True
        assert data["will_assign_to"] == ["admin@grunt.local"]

    async def test_list_assignment_logs_api(self, client, auth_headers, ctx, db_session):
        """Test the grunt.core.doctypes.assignment_log.assignment_log.list_logs method."""
        import datetime

        log_doc = {
            "doctype_affected": "Invoice",
            "document_id": "INV-TEST",
            "assigned_to": "admin@grunt.example.com",
            "assignment_method": "user",
            "status": "Success",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        await ctx.new_doc("AssignmentLog", log_doc)
        await db_session.commit()

        resp = await client.get(
            "/api/v1/method/grunt.core.doctypes.assignment_log.assignment_log.list_logs", 
            params={"doctype": "Invoice"},
            headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] >= 1
        assert any(log["document_id"] == "INV-TEST" for log in data["data"])
