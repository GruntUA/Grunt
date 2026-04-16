"""Report engine — runs Query/Script/List reports."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.doctypes.user.user import User

logger = structlog.get_logger()


class ReportEngine:
    async def run(
        self,
        report_name: str,
        filters: dict,
        user: User,
        session: AsyncSession,
    ) -> dict[str, Any]:
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["Report"])
        result = await session.execute(select(table).where(table.c.report_name == report_name))
        report = result.mappings().first()
        if not report:
            raise HTTPException(status_code=404, detail=f"Звіт '{report_name}' не знайдено")

        report_type = report["report_type"]
        if report_type == "Query":
            return await self._run_query_report({"query": report["query"] or ""}, filters, session)
        if report_type == "Script":
            return await self._run_script_report(
                {"script": report["script"] or "", "columns": report.get("columns")},
                filters,
                user,
                session,
            )
        if report_type == "List":
            doctype = report.get("doctype")
            if not doctype:
                raise HTTPException(400, detail="List report requires a DocType")
            return await self._run_list_report(
                doctype,
                {"columns": report.get("columns") or []},
                filters,
                user,
                session,
            )
        raise HTTPException(
            status_code=400,
            detail=f"Тип звіту '{report_type}' не підтримується",
        )

    # ── Query report ──────────────────────────────────────────────────────────

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
        rows = [dict(zip(keys, row, strict=False)) for row in result.fetchall()]
        elapsed = int((time.time() - start) * 1000)

        columns = [{"fieldname": k, "label": k, "fieldtype": "Text"} for k in keys]
        return {
            "columns": columns,
            "data": rows,
            "meta": {"rows": len(rows), "time_ms": elapsed},
        }

    # ── Script report ─────────────────────────────────────────────────────────

    async def _run_script_report(
        self,
        report: dict,
        filters: dict,
        user: User,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Execute a Python script in the sandbox and return {columns, data}.

        The script must populate ``grunt.result`` with a dict containing
        ``columns`` (list of ``{fieldname, label, fieldtype}``) and
        ``data`` (list of row dicts).

        Example script::

            rows = grunt.get_list(
                "Order",
                filters={"status": filters.get("status", "Open")},
                fields=["name", "customer", "amount"],
                limit=1000,
            )
            grunt.result = {
                "columns": [
                    {"fieldname": "name", "label": "Order", "fieldtype": "Text"},
                    {"fieldname": "customer", "label": "Customer", "fieldtype": "Text"},
                    {"fieldname": "amount", "label": "Amount", "fieldtype": "Float"},
                ],
                "data": rows,
            }
        """
        from grunt.app import grunt  # noqa: PLC0415
        from grunt.core.db.session import get_engine as _engine_factory  # noqa: PLC0415

        script_src = report.get("script", "").strip()
        if not script_src:
            raise HTTPException(400, detail="Скрипт не вказано")

        # Inject 'grunt.result' placeholder and 'filters' into the context
        from grunt.core.scripting.safe_globals import build_safe_globals  # noqa: PLC0415

        engine = await _engine_factory()
        tokens = grunt.set_context(session, engine, user)
        try:
            extra_globals = build_safe_globals()
            extra_globals["filters"] = filters

            # grunt.result will be set by the script
            _grunt_ns = extra_globals.get("grunt") or extra_globals.get("_grunt")

            start = time.time()
            exec(compile(script_src, "<script_report>", "exec"), extra_globals)  # noqa: S102
            elapsed = int((time.time() - start) * 1000)

            result: Any = extra_globals.get("result") or (
                _grunt_ns.result if _grunt_ns and hasattr(_grunt_ns, "result") else None
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("report.script_error", error=str(exc))
            raise HTTPException(500, detail=f"Помилка виконання скрипту: {exc}") from exc
        finally:
            grunt.reset_context(tokens)

        if not isinstance(result, dict) or "data" not in result:
            raise HTTPException(
                500,
                detail="Скрипт повинен присвоїти `result = {'columns': [...], 'data': [...]}`",
            )

        columns = result.get("columns") or [
            {"fieldname": k, "label": k, "fieldtype": "Text"}
            for k in (result["data"][0].keys() if result["data"] else [])
        ]
        return {
            "columns": columns,
            "data": result["data"],
            "meta": {"rows": len(result["data"]), "time_ms": elapsed},
        }

    # ── List / Dynamic report ─────────────────────────────────────────────────

    async def _run_list_report(
        self,
        doctype: str,
        report: dict,
        filters: dict,
        user: User,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Run a dynamic aggregate report against a DocType table.

        ``report["columns"]`` is a list of column definitions::

            [
                {"fieldname": "status", "label": "Status", "group_by": true},
                {"fieldname": "amount", "label": "Total Amount",
                 "aggregation": "sum", "fieldtype": "Float"},
                {"fieldname": "id", "label": "Count",
                 "aggregation": "count", "fieldtype": "Int"},
            ]

        Supported aggregations: ``count``, ``sum``, ``avg``, ``min``, ``max``.
        Columns without an aggregation are treated as GROUP BY columns when
        any aggregation column is present; otherwise a plain SELECT is used.
        """
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
        from grunt.core.permissions.rbac import permission_checker  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        # Permission check
        await permission_checker.require(user, dt, "read")

        col_defs: list[dict] = report.get("columns") or []

        # If no column definitions, fall back to in_list_view fields
        if not col_defs:
            col_defs = [
                {"fieldname": f.fieldname, "label": f.label}
                for f in dt.fields
                if getattr(f, "in_list_view", False)
            ]

        from collections.abc import Callable  # noqa: PLC0415, TC003
        agg_map: dict[str, Callable[..., Any]] = {
            "count": func.count,
            "sum": func.sum,
            "avg": func.avg,
            "min": func.min,
            "max": func.max,
        }

        has_aggregation = any(c.get("aggregation") for c in col_defs)
        select_cols = []
        group_by_cols = []
        result_columns = []

        for col_def in col_defs:
            fn = col_def["fieldname"]
            label = col_def.get("label", fn)
            agg = col_def.get("aggregation", "").lower()
            fieldtype = col_def.get("fieldtype", "Text")

            sa_col = table.c.get(fn)
            if sa_col is None:
                continue

            if agg and agg in agg_map:
                select_cols.append(agg_map[agg](sa_col).label(fn))
                result_columns.append({"fieldname": fn, "label": label, "fieldtype": fieldtype})
            elif has_aggregation:
                # Non-aggregated column when aggregation is present → GROUP BY
                select_cols.append(sa_col)
                group_by_cols.append(sa_col)
                result_columns.append({"fieldname": fn, "label": label, "fieldtype": fieldtype})
            else:
                select_cols.append(sa_col)
                result_columns.append({"fieldname": fn, "label": label, "fieldtype": fieldtype})

        if not select_cols:
            return {"columns": [], "data": [], "meta": {"rows": 0, "time_ms": 0}}

        stmt = select(*select_cols)

        # Apply filters (simple equality)
        for key, val in filters.items():
            col = table.c.get(key)
            if col is not None:
                stmt = stmt.where(col == val)

        # Row-level security
        from grunt.core.permissions.query import apply_permission_filter  # noqa: PLC0415

        stmt = apply_permission_filter(stmt, table, user, dt)

        if group_by_cols:
            stmt = stmt.group_by(*group_by_cols)

        stmt = stmt.limit(10_000)

        start = time.time()
        db_result = await session.execute(stmt)
        keys = list(db_result.keys())
        rows = [dict(zip(keys, row, strict=False)) for row in db_result.fetchall()]
        elapsed = int((time.time() - start) * 1000)

        return {
            "columns": result_columns,
            "data": rows,
            "meta": {"rows": len(rows), "time_ms": elapsed},
        }

    # ── Excel export ──────────────────────────────────────────────────────────

    async def export_excel(self, result: dict, report_name: str) -> bytes:
        try:
            from io import BytesIO  # noqa: PLC0415

            import openpyxl  # noqa: PLC0415
            from openpyxl.styles import Font  # noqa: PLC0415
        except ImportError as e:
            raise HTTPException(status_code=500, detail="openpyxl не встановлено") from e

        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = report_name[:31]

        columns = result.get("columns", [])
        data = result.get("data", [])

        # Header row
        for ci, col in enumerate(columns, 1):
            cell = ws.cell(row=1, column=ci, value=col.get("label", col["fieldname"]))
            cell.font = Font(bold=True)

        # Data rows
        for ri, row in enumerate(data, 2):
            for ci, col in enumerate(columns, 1):
                ws.cell(row=ri, column=ci, value=row.get(col["fieldname"]))

        # Auto-width
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()


report_engine = ReportEngine()
