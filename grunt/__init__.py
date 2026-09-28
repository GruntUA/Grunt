"""Ґрунт — Python Framework for Building CMS, ERP, and Business Apps.

The package namespace holds the request-scoped helpers an app module reaches
for most (``grunt.whitelist``, ``grunt.throw``, ``grunt.get_user``, ...).
Documents and database access live on the app facade::

    import grunt
    from grunt.app import grunt as grunt_app

    @grunt.whitelist()
    async def close(name: str) -> None:
        if not await grunt_app.db.exists("Invoice", name):
            grunt.throw("Invoice not found", code="NOT_FOUND")
        await grunt_app.save_doc("Invoice", name, {"status": "Closed"})
"""

from grunt.api.context import (
    clear_context,
    get_engine,
    get_session,
    get_site,
    get_user,
    set_engine,
    set_session,
    set_site,
    set_user,
    whitelist,
)
from grunt.api.messages import (
    ApplicationError,
    msgprint,
    msgprint_list,
    notify,
    notify_all,
    queue_email,
    throw,
)
from grunt.api.permissions import get_current_user
from grunt.log import log
from grunt.monitoring.error_log import record_error as log_error

__all__ = [
    "ApplicationError",
    "clear_context",
    "get_current_user",
    "get_engine",
    "get_session",
    "get_site",
    "get_user",
    "log",
    "log_error",
    "msgprint",
    "msgprint_list",
    "notify",
    "notify_all",
    "queue_email",
    "set_engine",
    "set_session",
    "set_site",
    "set_user",
    "throw",
    "whitelist",
]
