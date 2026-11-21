"""Naming series for the DocType and Document Naming Rule forms: the next name
a new document would get, and the counter behind it (:mod:`grunt.naming.service`)."""

from typing import Any

from grunt.api.context import whitelist
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.local import require_session
from grunt.metadata.registry import doctype_registry
from grunt.naming.service import naming_service


@whitelist(perm="grunt.manage_doctypes")
async def preview(
    doctype: str, pattern: str | None = None, doc: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``{pattern, prefix, current, next, fields}`` for *pattern* (the DocType's
    ``autoname`` when omitted) - nothing is counted. *doc* - field values for
    ``{field}`` tokens and ``naming_date_field``; the fields still missing are
    listed in ``fields``."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return await naming_service.preview(
        meta, pattern if pattern is not None else (meta.autoname or ""), doc, require_session()
    )


@whitelist(perm="grunt.manage_doctypes")
async def counter(prefix: str) -> int:
    """The last number given out under *prefix* (0 - none yet)."""
    return await naming_service.current(_prefix(prefix), require_session())


@whitelist(perm="grunt.manage_doctypes")
async def set_counter(prefix: str, current: int) -> int:
    """Set the last number given out under *prefix*; the next document gets +1.
    A number already taken is skipped when it comes up."""
    try:
        value = int(current)
    except TypeError, ValueError:
        throw(_("The counter must be a whole number"), "VALIDATION_ERROR")
    await naming_service.set_current(_prefix(prefix), value, require_session())
    return value


def _prefix(prefix: str) -> str:
    if not (prefix or "").strip():
        throw(_("Enter the series prefix"), "VALIDATION_ERROR")
    return prefix
