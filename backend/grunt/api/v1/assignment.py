"""Assignment Rules API endpoints — evaluate rules, test, and view logs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.assignment import assignment_service
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

router = APIRouter(prefix="/assignment-rules", tags=["assignment"])


@router.post("/{rule_id}/test")
async def test_assignment_rule(
    rule_id: str,
    test_doc: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
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
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        import json  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        # Load rule from DB
        rule_dt = await doctype_registry.get("AssignmentRule")
        rule_table = compile_doctype_to_table(rule_dt)

        result = await session.execute(
            select(rule_table).where(rule_table.c.id == rule_id)
        )
        row = result.mappings().one_or_none()

        if not row:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")

        rule = dict(row)
        doctype_target = rule.get("doctype_target")
        filters = {}
        try:
            filters = json.loads(rule.get("filters", "{}"))
        except json.JSONDecodeError:
            pass

        # Test if doc matches filters
        matched = assignment_service._match_filters(test_doc, filters)

        # Determine who would be assigned
        will_assign_to = []
        if matched:
            if rule.get("assign_to_user"):
                will_assign_to.append(rule["assign_to_user"])
            elif rule.get("assign_to_role"):
                # List users in role
                from grunt.core.auth.models import GruntUserRole  # noqa: PLC0415
                from sqlalchemy import select  # noqa: PLC0415

                res = await session.execute(
                    select(GruntUserRole.user_id).where(
                        GruntUserRole.role_name == rule["assign_to_role"]
                    )
                )
                user_ids = res.scalars().all()
                for u_id in user_ids:
                    from grunt.core.doctypes.User.User import get_user_by_id  # noqa: PLC0415

                    u = await get_user_by_id(u_id, session)
                    if u and u.is_active:
                        will_assign_to.append(u.email)

        matching_fields = [field for field in filters.keys() if field in test_doc]

        return {
            "success": True,
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

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/logs")
async def list_assignment_logs(
    doctype: str | None = None,
    document_id: str | None = None,
    assigned_to: str | None = None,
    status: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
    user: GruntUser = Depends(current_user),
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
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from sqlalchemy import select, and_  # noqa: PLC0415

        log_dt = await doctype_registry.get("AssignmentLog")
        log_table = compile_doctype_to_table(log_dt)

        # Build filters
        filters = []
        if doctype:
            filters.append(log_table.c.doctype_affected == doctype)
        if document_id:
            filters.append(log_table.c.document_id == document_id)
        if assigned_to:
            filters.append(log_table.c.assigned_to == assigned_to)
        if status:
            filters.append(log_table.c.status == status)

        # Query
        query = select(log_table)
        if filters:
            query = query.where(and_(*filters))
        query = query.order_by(log_table.c.timestamp.desc()).limit(limit)

        result = await session.execute(query)
        logs = [dict(row) for row in result.mappings().all()]

        return {
            "success": True,
            "data": logs,
            "count": len(logs),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
