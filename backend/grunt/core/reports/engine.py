"""Report engine — runs Query/Script/List reports."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()


class ReportEngine:
    async def run(
        self,
        report_name: str,
        filters: dict,
        user: "GruntUser",
        session: AsyncSession,
    ) -> dict[str, Any]:
        from grunt.core.db.system_tables import GruntReport  # noqa: PLC0415

        result = await session.execute(
            select(GruntReport).where(GruntReport.report_name == report_name)
        )
        report = result.scalar_one_or_none()
        if not report:
            raise HTTPException(status_code=404, detail=f"Звіт '{report_name}' не знайдено")

        report_type = report.report_type
        if report_type == "Query":
            return await self._run_query_report(
                {"query": report.query or ""}, filters, session
            )
        raise HTTPException(
            status_code=400,
            detail=f"Тип звіту '{report_type}' не підтримується",
        )

    async def _run_query_report(
        self,
        report: dict,
        filters: dict,
        session: AsyncSession,
    ) -> dict[str, Any]:
        query_str = report.get("query", "").strip()
        if not query_str:
            raise HTTPException(400, detail="Запит не вказано")

        # Security check — allow only SELECT
        try:
            import sqlparse  # noqa: PLC0415

            parsed = sqlparse.parse(query_str)
            for stmt in parsed:
                stmt_type = stmt.get_type()
                if stmt_type not in ("SELECT", None):
                    raise HTTPException(400, detail="Дозволено тільки SELECT")
        except ImportError:
            pass  # sqlparse not installed, skip check

        forbidden = ["drop", "delete", "update", "insert", "create", "alter", "truncate"]
        query_lower = query_str.lower()
        for word in forbidden:
            if word in query_lower:
                raise HTTPException(400, detail=f"Заборонено: {word.upper()}")

        start = time.time()
        result = await session.execute(text(query_str))
        keys = list(result.keys())
        rows = [dict(zip(keys, row)) for row in result.fetchall()]
        elapsed = int((time.time() - start) * 1000)

        columns = [{"fieldname": k, "label": k, "fieldtype": "Text"} for k in keys]
        return {
            "columns": columns,
            "data": rows,
            "meta": {"rows": len(rows), "time_ms": elapsed},
        }

    async def export_excel(self, result: dict, report_name: str) -> bytes:
        try:
            import openpyxl  # noqa: PLC0415
            from openpyxl.styles import Font  # noqa: PLC0415
            from io import BytesIO  # noqa: PLC0415
        except ImportError as e:
            raise HTTPException(
                status_code=500, detail="openpyxl не встановлено"
            ) from e

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = report_name[:31]  # type: ignore[union-attr]

        columns = result.get("columns", [])
        data = result.get("data", [])

        # Header row
        for ci, col in enumerate(columns, 1):
            cell = ws.cell(row=1, column=ci, value=col.get("label", col["fieldname"]))  # type: ignore[union-attr]
            cell.font = Font(bold=True)  # type: ignore[union-attr]

        # Data rows
        for ri, row in enumerate(data, 2):
            for ci, col in enumerate(columns, 1):
                ws.cell(row=ri, column=ci, value=row.get(col["fieldname"]))  # type: ignore[union-attr]

        # Auto-width
        for col in ws.columns:  # type: ignore[union-attr]
            max_len = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)  # type: ignore[union-attr]

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()


report_engine = ReportEngine()
