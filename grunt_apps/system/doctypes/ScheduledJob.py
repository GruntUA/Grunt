from typing import Any, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.document.controller import DocumentController
from grunt.core.metadata.registry import doctype_registry
from grunt.core.metadata.compiler import compile_doctype_to_table


class ScheduledJobController(DocumentController):
    """Virtual DocType controller for Scheduled Jobs (ServerScript with Scheduler Event type)."""

    async def get_list(
        self,
        session: AsyncSession,
        filters: Dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str | None = None,
        fields: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """Get list of scheduled jobs from ServerScript table."""
        table = compile_doctype_to_table(doctype_registry._doctypes["ServerScript"])

        stmt = (
            select(table)
            .where(table.c.script_type == "Scheduler Event")
            .limit(limit)
            .offset(offset)
        )

        result = await session.execute(stmt)
        rows = result.mappings().all()

        # Transform ServerScript rows to ScheduledJob format
        jobs = []
        for row in rows:
            job = {
                "job_id": row["name"],
                "name": row["name"],
                "enabled": row["is_enabled"],
                "cron_expression": row["cron"] or "",
                "next_run_at": None,  # TODO: calculate from cron
                "last_run_at": None,  # TODO: track execution
                "status": "Pending",  # TODO: track status
                "last_error": None,  # TODO: track errors
                "run_count": 0,  # TODO: track count
                "executor": "server_script",  # Fixed for now
                "params": {},  # ServerScript doesn't have params
            }
            jobs.append(job)

        return jobs

    async def get_doc(self, session: AsyncSession, name: str) -> Dict[str, Any] | None:
        """Get single scheduled job by name."""
        table = compile_doctype_to_table(doctype_registry._doctypes["ServerScript"])

        stmt = (
            select(table)
            .where(table.c.script_type == "Scheduler Event")
            .where(table.c.name == name)
        )

        result = await session.execute(stmt)
        row = result.mappings().first()

        if not row:
            return None

        # Transform to ScheduledJob format
        return {
            "job_id": row["name"],
            "name": row["name"],
            "enabled": row["is_enabled"],
            "cron_expression": row["cron"] or "",
            "next_run_at": None,
            "last_run_at": None,
            "status": "Pending",
            "last_error": None,
            "run_count": 0,
            "executor": "server_script",
            "params": {},
        }

    async def create_doc(self, session: AsyncSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new scheduled job (actually creates ServerScript)."""
        # This would create a ServerScript with script_type = "Scheduler Event"
        # For now, return mock response
        return {
            "job_id": data.get("name", "new_job"),
            "name": data.get("name", "new_job"),
            "enabled": data.get("enabled", True),
            "cron_expression": data.get("cron_expression", ""),
            "status": "Pending",
        }

    async def update_doc(self, session: AsyncSession, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update scheduled job (actually updates ServerScript)."""
        # This would update the corresponding ServerScript
        # For now, return mock response
        return {
            "job_id": name,
            "name": name,
            "enabled": data.get("enabled", True),
            "cron_expression": data.get("cron_expression", ""),
            "status": "Pending",
        }

    async def delete_doc(self, session: AsyncSession, name: str) -> None:
        """Delete scheduled job (actually deletes ServerScript)."""
        # This would delete the corresponding ServerScript
        pass