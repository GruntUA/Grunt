"""``ErrorLog`` controller — read-only journal of unhandled errors.

Rows are written exclusively through
:func:`grunt.monitoring.error_log.record_error` (exposed to apps as
``grunt.log_error``). No role is granted ``write``/``create`` on the DocType,
so the generic CRUD API already keeps the journal append-only; this controller
only exists to give the record a typed shape.
"""

from __future__ import annotations

from grunt.document.base import Document


class ErrorLog(Document):
    title: str
    error_type: str | None
    context: str | None
    app: str | None
    method: str | None
    user: str | None
    http_status: int | None
    request_method: str | None
    request_path: str | None
    request_id: str | None
    reference_doctype: str | None
    reference_name: str | None
    error_message: str | None
    traceback: str | None
