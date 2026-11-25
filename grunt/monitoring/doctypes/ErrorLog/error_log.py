"""``ErrorLog`` controller - read-only journal of unhandled errors.

Rows are written exclusively through
:func:`grunt.monitoring.error_log.record_error` (exposed to apps as
``grunt.log_error``). No role is granted ``write``/``create`` on the DocType,
so the generic CRUD API already keeps the journal append-only; this controller
only exists to give the record a typed shape.
"""

from grunt.document.base import Document


class ErrorLog(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str | None = None  # Error
    error_type: str | None = None  # Type
    context: str | None = None  # Context
    app: str | None = None  # App
    method: str | None = None  # Method / route
    user: str | None = None  # User
    request_method: str | None = None  # HTTP method
    http_status: int | None = None  # Response code
    request_path: str | None = None  # Path
    request_id: str | None = None  # Request ID
    reference_doctype: str | None = None  # Document type
    reference_name: str | None = None  # Document
    error_message: str | None = None  # Message
    traceback: str | None = None  # Stack trace

    # end: auto-generated types
