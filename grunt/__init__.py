"""Ґрунт - Python Framework for Building CMS, ERP, and Business Apps.

One namespace for app code::

    import grunt

    @grunt.whitelist()
    async def close(name: str) -> None:
        if not await grunt.db.exists("Invoice", name):
            grunt.throw("Invoice not found", code="NOT_FOUND")
        await grunt.save_doc("Invoice", name, {"status": "Closed"})

The request-scoped helpers are imported first: modules loaded while
``grunt.app`` initialises (document mixins and their ``@grunt.whitelist()``
decorators) see this package half-built, with those names already bound.
The document API is bound from the :class:`~grunt.app.GruntApp` singleton last.
"""

# isort: off
# `log` and `_` first: modules loaded below may already `from grunt import _, log`.
# `log` before `_`: importing grunt.i18n already pulls in grunt.metadata, whose
# `from grunt import log` would otherwise get the grunt.log *module*.
from grunt.log import log
from grunt.i18n import _
from grunt.api.context import get_engine, get_session, get_user, whitelist
from grunt.api.messages import msgprint, throw
from grunt.monitoring.error_log import record_error as log_error

from grunt.app import grunt as _app  # after the helpers above - see the module docstring
# isort: on

# Document & database API (GruntApp)
db = _app.db
query_cache = _app.query_cache
doc_cache = _app.doc_cache

context = _app.context
system_context = _app.system_context
bootstrap_context = _app.bootstrap_context
set_context = _app.set_context
reset_context = _app.reset_context

get_doc = _app.get_doc
find_doc = _app.find_doc
get_doc_instance = _app.get_doc_instance
new_doc = _app.new_doc
save_doc = _app.save_doc
delete_doc = _app.delete_doc
rename_doc = _app.rename_doc
copy_doc = _app.copy_doc
submit = _app.submit
get_list = _app.get_list
get_all = _app.get_all
count = _app.count
exists = _app.exists
get_value = _app.get_value
set_value = _app.set_value
get_single = _app.get_single
bulk_insert = _app.bulk_insert
bulk_update = _app.bulk_update
bulk_delete_docs = _app.bulk_delete_docs
get_meta = _app.get_meta
has_permission = _app.has_permission

notify = _app.notify
publish = _app.publish
enqueue_doc = _app.enqueue_doc
render_template = _app.render_template

__all__ = [
    "_",
    "bootstrap_context",
    "bulk_delete_docs",
    "bulk_insert",
    "bulk_update",
    "context",
    "copy_doc",
    "count",
    "db",
    "delete_doc",
    "doc_cache",
    "enqueue_doc",
    "exists",
    "find_doc",
    "get_all",
    "get_doc",
    "get_doc_instance",
    "get_engine",
    "get_list",
    "get_meta",
    "get_session",
    "get_single",
    "get_user",
    "get_value",
    "has_permission",
    "log",
    "log_error",
    "msgprint",
    "new_doc",
    "notify",
    "publish",
    "query_cache",
    "rename_doc",
    "render_template",
    "reset_context",
    "save_doc",
    "set_context",
    "set_value",
    "submit",
    "system_context",
    "throw",
    "whitelist",
]
