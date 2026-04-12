"""Assignment Rules API endpoints — evaluate rules, test, and view logs."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok, ok_list
from grunt.app import grunt
from grunt.core.assignment import assignment_service

router = GruntRouter(prefix="/assignment-rules", tags=["assignment"])


class TestRuleRequest(BaseModel):
    test_doc: dict[str, Any]


@router.post("/{rule_id}/test")
async def test_assignment_rule(
    rule_id: str,
    body: TestRuleRequest,
) -> dict[str, Any]:
    """Test an assignment rule against a sample document.

    Request:
    ```json
    {
      "test_doc": {
        "status": "Draft",
        "amount": 5000,
        "title": "Sample Invoice"
      }
    }
    ```

    Response:
    ```json
    {
      "success": true,
      "rule_id": "rule-123",
      "doctype_target": "Invoice",
      "filters": {"status": "Draft", "amount": {">": 1000}},
      "matched": true,
      "matching_fields": ["status", "amount"],
      "will_assign_to": ["finance@company.com"],
      "message": "Rule matches! Will assign to 1 user"
    }
    ```
    """
    try:
        try:
            rule = await grunt.get_doc("AssignmentRule", rule_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found") from exc
            raise

        doctype_target = rule.get("doctype_target")
        filters = {}
        with contextlib.suppress(json.JSONDecodeError):
            filters = json.loads(rule.get("filters", "{}"))

        # Test if doc matches filters
        test_doc = body.test_doc
        matched = assignment_service._match_filters(test_doc, filters)

        # Determine who would be assigned
        will_assign_to = []
        if matched:
            if rule.get("assign_to_user"):
                will_assign_to.append(rule["assign_to_user"])
            elif rule.get("assign_to_role"):
                # List users in role
                ur_rows = await grunt.get_list(
                    "UserRole",
                    filters={"role_name": rule["assign_to_role"]},
                    fields=["user_id"],
                    limit=500,
                )

                from grunt.core.doctypes.user.user import get_user_by_id

                session = grunt._require_session()

                for ur in ur_rows:
                    u = await get_user_by_id(ur["user_id"], session)
                    if u and u.is_active:
                        will_assign_to.append(u.email)

        matching_fields = [field for field in filters if field in test_doc]

        return ok(
            rule_id=rule_id,
            doctype_target=doctype_target,
            filters=filters,
            matched=matched,
            matching_fields=matching_fields,
            will_assign_to=will_assign_to,
            message=(
                f"Rule matches! Will assign to {len(will_assign_to)} user(s)"
                if matched
                else "Rule does not match"
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/logs")
async def list_assignment_logs(
    doctype: str | None = None,
    document_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List assignment logs with filters.

    Query params:
    - `doctype`: Filter by DocType affected
    - `document_id`: Filter by document ID
    - `assigned_to`: Filter by user assigned to
    - `status`: Filter by status (Success/Failed)
    - `limit`: Max records (default 100)
    """
    try:
        # Build filters
        filters = {}
        if doctype:
            filters["doctype_affected"] = doctype
        if document_id:
            filters["document_id"] = document_id
        if assigned_to:
            filters["assigned_to"] = assigned_to
        if status:
            filters["status"] = status

        logs = await grunt.get_list(
            "AssignmentLog", filters=filters, limit=limit, order_by="timestamp", order="desc"
        )
        total = await grunt.count("AssignmentLog", filters=filters)

        return ok_list(logs, total=total)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
