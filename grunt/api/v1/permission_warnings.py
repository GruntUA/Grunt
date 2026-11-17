"""Access settings that probably don't do what was meant - for the DocType and
Role forms (:mod:`grunt.permissions.warnings`)."""

from typing import Any

from grunt.api.context import whitelist
from grunt.errors import not_found
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.permissions.warnings import doctype_warnings, role_warnings


@whitelist(perm="grunt.manage_permissions")
async def for_doctype(doctype: str) -> list[dict[str, Any]]:
    """``[{code, message}]`` for *doctype*'s rules and fields."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return await doctype_warnings(meta)


@whitelist(perm="grunt.manage_permissions")
async def for_role(role: str) -> list[dict[str, Any]]:
    """``[{code, message}]`` for *role*: nobody holds it, it grants nothing."""
    return await role_warnings(role)
