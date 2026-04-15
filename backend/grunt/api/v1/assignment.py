"""Assignment Rules API whitelisted methods."""

from __future__ import annotations
import contextlib
import json
from typing import Any
import grunt
from grunt.app import grunt as grunt_app

@grunt.whitelist()
async def test_rule(rule_id: str, test_doc: dict[str, Any]) -> dict[str, Any]:
    """Test an assignment rule against a sample document."""
    from grunt.core.assignment import assignment_service

    try:
        rule = await grunt_app.get_doc("AssignmentRule", rule_id)
        doctype_target = rule.get("doctype_target")
        filters = {}
        if isinstance(rule.get("filters"), str):
            with contextlib.suppress(json.JSONDecodeError):
                filters = json.loads(rule.get("filters", "{}"))
        else:
            filters = rule.get("filters") or {}

        # Test if doc matches filters
        matched = assignment_service._match_filters(test_doc, filters)

        # Determine who would be assigned
        will_assign_to = []
        if matched:
            if rule.get("assign_to_user"):
                will_assign_to.append(rule["assign_to_user"])
            elif rule.get("assign_to_role"):
                ur_rows = await grunt_app.get_list(
                    "UserRole",
                    filters={"role_name": rule["assign_to_role"]},
                    fields=["user_id"],
                    limit=500,
                )
                from grunt.core.doctypes.user.user import get_user_by_id
                session = grunt_app._require_session()
                for ur in ur_rows:
                    u = await get_user_by_id(ur["user_id"], session)
                    if u and u.is_active:
                        will_assign_to.append(u.email)

        matching_fields = [field for field in filters if field in test_doc]

        return {
            "rule_id": rule_id,
            "doctype_target": doctype_target,
            "filters": filters,
            "matched": matched,
            "matching_fields": matching_fields,
            "will_assign_to": will_assign_to,
            "message": (
                f"Rule matches! Will assign to {len(will_assign_to)} user(s)"
                if matched
                else "Rule does not match"
            ),
        }
    except Exception as exc:
        grunt_app.throw(str(exc))

@grunt.whitelist()
async def list_logs(
    doctype: str | None = None,
    document_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List assignment logs with filters."""
    filters = {}
    if doctype:
        filters["doctype_affected"] = doctype
    if document_id:
        filters["document_id"] = document_id
    if assigned_to:
        filters["assigned_to"] = assigned_to
    if status:
        filters["status"] = status

    logs = await grunt_app.get_list(
        "AssignmentLog", filters=filters, limit=int(limit), order_by="timestamp", order="desc"
    )
    total = await grunt_app.count("AssignmentLog", filters=filters)

    return {"data": logs, "count": total}
