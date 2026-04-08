"""Tests for the Assignment Rules system."""

from __future__ import annotations

import pytest

from grunt.core.assignment import AssignmentService


class TestAssignmentFilters:
    """Test filter matching logic."""

    def setup_method(self):
        self.service = AssignmentService()

    def test_simple_match(self):
        """Simple field match: {"status": "Draft"}."""
        doc = {"id": "1", "name": "DOC-001", "status": "Draft", "title": "Test"}
        filters = {"status": "Draft"}
        assert self.service._match_filters(doc, filters) is True

    def test_simple_no_match(self):
        """Field doesn't match."""
        doc = {"status": "Submitted"}
        filters = {"status": "Draft"}
        assert self.service._match_filters(doc, filters) is False

    def test_multiple_filters_and(self):
        """Multiple filters (AND logic)."""
        doc = {"status": "Draft", "total": 5000, "qty": 10}
        filters = {"status": "Draft", "total": 5000}
        assert self.service._match_filters(doc, filters) is True

    def test_multiple_filters_and_fail(self):
        """One of multiple filters fails."""
        doc = {"status": "Draft", "total": 500}
        filters = {"status": "Draft", "total": 5000}
        assert self.service._match_filters(doc, filters) is False

    def test_operator_greater_than(self):
        """Operator: {">": 1000}."""
        doc = {"amount": 1500}
        filters = {"amount": {">": 1000}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_greater_than_fail(self):
        """Operator fails."""
        doc = {"amount": 900}
        filters = {"amount": {">": 1000}}
        assert self.service._match_filters(doc, filters) is False

    def test_operator_gte(self):
        """Operator: {">=": 1000}."""
        doc = {"amount": 1000}
        filters = {"amount": {">=": 1000}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_lt(self):
        """Operator: {"<": 100}."""
        doc = {"priority": 50}
        filters = {"priority": {"<": 100}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_lte(self):
        """Operator: {"<=": 100}."""
        doc = {"priority": 100}
        filters = {"priority": {"<=": 100}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_not_equal(self):
        """Operator: {"!=": "Draft"}."""
        doc = {"status": "Submitted"}
        filters = {"status": {"!=": "Draft"}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_not_equal_fail(self):
        """Operator fails."""
        doc = {"status": "Draft"}
        filters = {"status": {"!=": "Draft"}}
        assert self.service._match_filters(doc, filters) is False

    def test_operator_in(self):
        """Operator: {"in": ["Draft", "Pending"]}."""
        doc = {"status": "Draft"}
        filters = {"status": {"in": ["Draft", "Pending"]}}
        assert self.service._match_filters(doc, filters) is True

    def test_operator_in_fail(self):
        """Operator fails."""
        doc = {"status": "Submitted"}
        filters = {"status": {"in": ["Draft", "Pending"]}}
        assert self.service._match_filters(doc, filters) is False

    def test_empty_filters(self):
        """Empty filters always match (catch-all rule)."""
        doc = {"status": "Anything"}
        filters = {}
        assert self.service._match_filters(doc, filters) is True

    def test_none_filters(self):
        """None filters are treated as empty and match all."""
        doc = {"status": "Anything"}
        assert self.service._match_filters(doc, None) is True

    def test_missing_field_in_doc(self):
        """Field doesn't exist in document."""
        doc = {"status": "Draft"}
        filters = {"amount": 1000}
        assert self.service._match_filters(doc, filters) is False

    def test_complex_filters(self):
        """Complex real-world filters."""
        doc = {"status": "Draft", "amount": 5000, "priority": 1}
        filters = {
            "status": "Draft",
            "amount": {">=": 3000},
            "priority": {"!=": 3},
        }
        assert self.service._match_filters(doc, filters) is True

    def test_complex_filters_fail(self):
        """Complex filters fail on one condition."""
        doc = {"status": "Draft", "amount": 2000, "priority": 1}
        filters = {
            "status": "Draft",
            "amount": {">=": 3000},  # ← This fails
            "priority": {"!=": 3},
        }
        assert self.service._match_filters(doc, filters) is False


class TestAssignmentIntegration:
    """Integration tests with async operations."""

    @pytest.mark.asyncio
    async def test_evaluate_and_assign_no_rules(self, client, auth_headers, setup_db):
        """When no rules exist, nothing happens."""
        # No AssignmentRules in DB
        # Call evaluate_and_assign
        from grunt.app import grunt
        from grunt.core.assignment import assignment_service
        from grunt.core.auth.models import SYSTEM_USER
        from grunt.core.db.session import get_session

        async for session in get_session():
            _tokens = grunt.set_context(session, None, SYSTEM_USER)
            try:
                await assignment_service.evaluate_and_assign(
                    doctype="Invoice",
                    doc={"id": "1", "status": "Draft"},
                )
            finally:
                grunt.reset_context(_tokens)
            break

    @pytest.mark.asyncio
    async def test_evaluate_and_assign_with_match(self, client, auth_headers, setup_db):
        """When a rule matches, assignment is triggered."""
        # This test would require:
        # 1. Create AssignmentRule doctype
        # 2. Insert a rule into DB
        # 3. Call evaluate_and_assign
        # 4. Verify ToDo was created
        pass


class TestAssignmentAPI:
    """Test assignment endpoints logic."""

    @pytest.mark.asyncio
    async def test_test_assignment_rule(self, client, auth_headers, setup_db):
        """Test the POST /api/v1/assignment-rules/{rule_id}/test endpoint."""
        rule_data = {
            "name": "Test Rule API",
            "doctype_target": "Invoice",
            "filters": '{"status": "Draft"}',
            "assign_to_user": "admin@grunt.local",
            "enabled": True,
        }
        resp = await client.post(
            "/api/v1/docs/AssignmentRule", headers=auth_headers, json=rule_data
        )
        assert resp.status_code in (200, 201), resp.text
        rule_id = resp.json()["data"]["id"]

        test_doc = {"status": "Draft", "amount": 100}
        resp = await client.post(
            f"/api/v1/assignment-rules/{rule_id}/test",
            headers=auth_headers,
            json={"test_doc": test_doc},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["matched"] is True
        assert data["will_assign_to"] == ["admin@grunt.local"]

    @pytest.mark.asyncio
    async def test_list_assignment_logs(self, client, auth_headers, db_session, engine):
        """Test the GET /api/v1/assignment-rules/logs endpoint."""
        import datetime

        from grunt.app import grunt
        from grunt.core.auth.models import SYSTEM_USER

        log_doc = {
            "doctype_affected": "Invoice",
            "document_id": "INV-TEST",
            "assigned_to": "admin@grunt.example.com",
            "assignment_method": "user",
            "status": "Success",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        _tokens = grunt.set_context(db_session, engine, SYSTEM_USER)
        try:
            await grunt.new_doc("AssignmentLog", log_doc)
            await db_session.commit()
        finally:
            grunt.reset_context(_tokens)

        resp = await client.get(
            "/api/v1/assignment-rules/logs?doctype=Invoice", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1
        assert any(log["document_id"] == "INV-TEST" for log in data["data"])
