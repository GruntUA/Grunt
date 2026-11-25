"""Report RPC methods - grunt.reports.doctypes.Report.report.{run, prepare,
fields, preview, export_xlsx}

Plain CRUD on the ``Report`` doctype (list/get/create/update/delete) goes
through the generic ``/api/v1/docs/Report`` REST endpoints - ``Report`` is a
regular registered DocType, so that works with no custom code, and is
enforced by ``Report.json``'s ``permissions`` (read: any authenticated user;
write/create/delete: nobody but System Manager - see that file). The RPC methods
below cover only what generic CRUD can't: running a report (arbitrary
SQL/script/list execution), the fields the builder may offer, and exporting
the result. ``run``/``export_xlsx``
look up the report by its human ``report_name`` (unique but distinct from the
doctype's internal ``name``/id), matching ``ReportEngine.run``'s lookup key
and every existing frontend reference to a report (shortcuts, sidebar links,
print scripting) - see project notes for why that identifier was kept rather
than switched to the internal id.
"""

from datetime import datetime
from typing import Any

from fastapi.responses import Response

from grunt.api.context import whitelist
from grunt.auth.current import acting_user
from grunt.document.base import Document
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.local import require_session, user_email
from grunt.metadata.registry import doctype_registry
from grunt.permissions.access_log import record_access
from grunt.permissions.rbac import permission_checker
from grunt.reports import prepared
from grunt.reports.engine import report_engine
from grunt.reports.joins import report_fields


class Report(Document):
    """DocType controller for Report."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    report_name: str  # Name
    report_type: str  # Type
    ref_doctype: str | None = None  # Document type
    columns: Any | None = None  # Columns (JSON)
    filters_config: Any | None = None  # Filter configuration (JSON)
    chart_config: Any | None = None  # Chart configuration (JSON)
    conditions: Any | None = None  # Conditions
    sort_by: str | None = None  # Sort by
    sort_order: str | None = None  # Sort order
    row_limit: int | None = None  # Row limit
    query: str | None = None  # SQL
    script: str | None = None  # Script
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    disabled: bool | None = None  # Disabled
    prepared_report: bool | None = None  # Prepared report
    timeout: int | None = None  # Timeout, sec
    schedule_frequency: str | None = None  # Send
    schedule_recipients: str | None = None  # Recipients
    schedule_filters: Any | None = None  # Filters
    last_sent_at: datetime | None = None  # Last sent

    # end: auto-generated types

    roles: list[str] | None


@whitelist()
async def run(name: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a report and return results.

    A prepared report isn't run here: the result is the latest one calculated
    for these filters (empty until then), and ``prepared`` tells its state -
    :func:`prepare` queues a new calculation.
    """
    user, session = user_email(), require_session()
    report = await report_engine.load(name, user, session)
    if not report.get("prepared_report"):
        return await report_engine.execute(report, filters or {}, user, session)
    return await _prepared_result(report, filters or {}, user)


async def _prepared_result(report: dict[str, Any], filters: dict[str, Any], user: str) -> dict:
    current = await prepared.latest(report["name"], user, filters)
    result = (await prepared.load_result(current) if current else None) or {
        "columns": [],
        "data": [],
        "meta": {"rows": 0, "time_ms": 0},
    }
    result["prepared"] = _prepared_state(current)
    return result


def _prepared_state(row: dict[str, Any] | None) -> dict[str, Any]:
    keys = ("name", "status", "created_at", "finished_at", "rows", "time_ms", "error")
    return {k: row.get(k) for k in keys} if row else {"status": None}


@whitelist()
async def prepare(name: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Queue a background calculation of the prepared report *name* for these
    *filters*; the user gets a ``prepared_report`` realtime event when it is done."""
    user, session = user_email(), require_session()
    report = await report_engine.load(name, user, session)
    if not report.get("prepared_report"):
        throw(_("Report “%(name)s” is not a prepared report") % {"name": name})
    return _prepared_state(await prepared.prepare(report, filters or {}, user))


@whitelist()
async def fields(doctype: str) -> list[dict[str, Any]]:
    """The fields the report builder may offer for *doctype* - those a report
    can read for the current user (:func:`grunt.reports.joins.report_fields`)."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = acting_user()
    await permission_checker.require(meta, "read", user=user.email)
    return await report_fields(meta, user.email)


@whitelist()
async def preview(
    doctype: str,
    columns: list[dict[str, Any]] | None = None,
    filters: dict[str, Any] | None = None,
    conditions: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    row_limit: int | None = None,
) -> dict[str, Any]:
    """Execute an ad-hoc List report configuration (the builder's preview)."""
    result = await report_engine._run_list_report(
        doctype,
        {
            "columns": columns or [],
            "conditions": conditions or [],
            "sort_by": sort_by,
            "sort_order": sort_order,
            "row_limit": row_limit,
        },
        filters or {},
        user_email(),
        require_session(),
    )
    return result


@whitelist()
async def export_xlsx(
    name: str,
    filters: dict[str, Any] | None = None,
    token: str | None = None,  # unused: absorbs ?token= query param consumed by auth, not by us
) -> Response:
    """Run a report and return the result as an xlsx file download - a prepared
    report's latest result for these filters."""
    user, session = user_email(), require_session()
    report = await report_engine.load(name, user, session)
    if report.get("prepared_report"):
        result = await _prepared_result(report, filters or {}, user)
        if result["prepared"].get("status") != "Completed":
            throw(_("The report hasn't been calculated for these filters yet"))
    else:
        result = await report_engine.execute(report, filters or {}, user, session)
    xlsx_bytes = await report_engine.export_excel(result, name)
    await record_access(
        "Report",
        "Report",
        doc_id=name,
        file_format="xlsx",
        rows=len(result.get("data") or []),
        filters=filters or None,
    )
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name[:50]}.xlsx"'},
    )
