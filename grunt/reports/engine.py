"""Report engine — runs Query/Script/List reports."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

import structlog
from fastapi import HTTPException
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from collections.abc import Callable

    from openpyxl.cell import Cell
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User

logger = structlog.get_logger()


class ReportEngine:
    async def run(
        self,
        report_name: str,
        filters: dict,
        user: User,
        session: AsyncSession,
    ) -> dict[str, Any]:
        from grunt.app import grunt

        async with grunt.context(session, None, user):
            rows = await grunt.get_list(
                "Report",
                filters={"report_name": report_name},
                fields=["report_name", "report_type", "query", "script", "columns", "doctype"],
                limit=1,
            )
        report = rows[0] if rows else None
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
            import sqlparse

            parsed = sqlparse.parse(query_str)
            for stmt in parsed:
                stmt_type = stmt.get_type()
                if stmt_type not in ("SELECT", None):
                    raise HTTPException(400, detail="Дозволено тільки SELECT")
        except ImportError:
            logger.debug("suppressed_expected_error", exc_info=True)

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

        The sandbox has **no** database or network access. The script must
        satisfy exactly one of two output contracts:

        1. ``result = {"columns": [...], "data": [...]}`` — the script builds
           the rows itself from ``filters`` and plain Python. ``columns`` is a
           list of ``{fieldname, label, fieldtype}``; omit it to derive plain
           text columns from the first row's keys.
        2. ``query = "SELECT ..."`` — the script only *chooses* a read-only
           SQL statement (typically per ``db_dialect``), which the engine
           then runs through the same SELECT-only guard as a Query report.

        Injected globals: ``filters`` (dict) and ``db_dialect`` (str, e.g.
        ``"sqlite"`` / ``"postgresql"``).

        Example — portable "size per table" report::

            if db_dialect == "postgresql":
                query = "SELECT ... pg_total_relation_size(c.oid) ..."
            else:
                query = "SELECT ... FROM dbstat ..."
        """
        from grunt.app import grunt
        from grunt.db.session import get_engine as _engine_factory

        script_src = report.get("script", "").strip()
        if not script_src:
            raise HTTPException(400, detail="Скрипт не вказано")

        from grunt.scripting.safe_globals import build_safe_globals, compile_script

        # Not plain compile()+exec(): see safe_globals.py's module docstring
        # — a restricted __builtins__ dict alone doesn't stop attribute
        # traversal (e.g. str.__mro__[-1].__subclasses__()) from reaching
        # subprocess.Popen and similar regardless of what's in __builtins__.
        # compile_script() (RestrictedPython) is the actual sandbox; this
        # exec() must only ever run code it produced.
        compiled = compile_script(script_src)
        if compiled.errors:
            raise HTTPException(400, detail="; ".join(compiled.errors))

        engine = await _engine_factory()
        async with grunt.context(session, engine, user):
            extra_globals = build_safe_globals()
            extra_globals["filters"] = filters
            try:
                extra_globals["db_dialect"] = session.bind.dialect.name
            except AttributeError:
                extra_globals["db_dialect"] = ""

            # grunt.result will be set by the script
            _grunt_ns = extra_globals.get("grunt") or extra_globals.get("_grunt")

            start = time.time()
            try:
                exec(compiled.code, extra_globals)
            except HTTPException:
                raise
            except Exception as exc:
                logger.error("report.script_error", error=str(exc))
                raise HTTPException(500, detail=f"Помилка виконання скрипту: {exc}") from exc
            elapsed = int((time.time() - start) * 1000)

            result: Any = extra_globals.get("result") or (
                _grunt_ns.result if _grunt_ns and hasattr(_grunt_ns, "result") else None
            )
            script_query = extra_globals.get("query")

        if not isinstance(result, dict) or "data" not in result:
            # Contract 2: the script only picked a read-only SQL statement.
            if isinstance(script_query, str) and script_query.strip():
                return await self._run_query_report(
                    {"query": script_query}, filters, session
                )
            raise HTTPException(
                500,
                detail=(
                    "Скрипт повинен присвоїти `result = {'columns': [...], 'data': [...]}` "
                    "або `query = 'SELECT ...'`"
                ),
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
        from grunt.metadata.compiler import compile_doctype_to_table
        from grunt.metadata.registry import doctype_registry
        from grunt.permissions.rbac import permission_checker

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)

        # Permission check
        await permission_checker.require(user, dt, "read")

        col_defs: list[dict] = report.get("columns") or []

        # If no column definitions, fall back to in_list_view fields
        if not col_defs:
            from grunt.document.meta import Meta

            col_defs = [
                {"fieldname": f.fieldname, "label": f.label}
                for f in Meta(dt).get_list_view_fields()
            ]

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

        # Apply filters — operator-aware, same vocabulary as list views:
        # ``field__gte`` / ``__like`` / ``__ne`` / … ; a bare ``field`` means
        # equality. Empty values are dropped so an untouched filter is a no-op.
        from grunt.db.api import build_clauses

        active_filters = {k: v for k, v in filters.items() if v not in (None, "", [])}
        for clause in build_clauses(table, active_filters):
            stmt = stmt.where(clause)

        # Row-level security
        from grunt.permissions.query import apply_permission_filter

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
            from io import BytesIO

            import openpyxl
            from openpyxl.styles import Font
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
        from grunt.io.exporters.sanitize import escape_formula

        for ri, row in enumerate(data, 2):
            for ci, col in enumerate(columns, 1):
                cell_value = row.get(col["fieldname"])
                if isinstance(cell_value, str):
                    cell_value = escape_formula(cell_value)
                ws.cell(row=ri, column=ci, value=cell_value)

        # Auto-width
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=0)
            ws.column_dimensions[cast("Cell", col[0]).column_letter].width = min(max_len + 2, 50)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()


report_engine = ReportEngine()
