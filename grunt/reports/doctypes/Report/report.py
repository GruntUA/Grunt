"""Report RPC methods - grunt.reports.doctypes.Report.report.{run,fields,preview,export_xlsx}

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

import grunt
from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import require_session
from grunt.metadata.registry import doctype_registry
from grunt.permissions.rbac import permission_checker
from grunt.reports.engine import report_engine
from grunt.reports.joins import report_fields


class Report(Document):
    """DocType controller for Report."""

    report_name: str | None
    report_type: str | None
    ref_doctype: str | None
    columns: dict | None
    filters_config: dict | None
    chart_config: dict | None
    conditions: dict | None
    sort_by: str | None
    sort_order: str | None
    row_limit: int | None
    query: str | None
    script: str | None
    is_standard: bool | None
    app: str | None
    schedule_frequency: str | None
    schedule_recipients: str | None
    schedule_filters: dict | None
    last_sent_at: datetime | None


@whitelist()
async def run(name: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a report and return results."""
    result = await report_engine.run(name, filters or {}, grunt.get_user().email, require_session())
    return result


@whitelist()
async def fields(doctype: str) -> list[dict[str, Any]]:
    """The fields the report builder may offer for *doctype* - those a report
    can read for the current user (:func:`grunt.reports.joins.report_fields`)."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    user = grunt.get_user()
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
        grunt.get_user().email,
        require_session(),
    )
    return result


@whitelist()
async def export_xlsx(
    name: str,
    filters: dict[str, Any] | None = None,
    token: str | None = None,  # unused: absorbs ?token= query param consumed by auth, not by us
) -> Response:
    """Run a report and return the result as an xlsx file download."""
    result = await report_engine.run(name, filters or {}, grunt.get_user().email, require_session())
    xlsx_bytes = await report_engine.export_excel(result, name)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name[:50]}.xlsx"'},
    )
