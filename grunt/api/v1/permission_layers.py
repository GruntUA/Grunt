"""The site's access rules against the app's (PERMISSIONS_PLAN step 6e):
the difference, and putting the app's rules back
(:mod:`grunt.metadata.permission_layers`)."""

from typing import Any

from grunt.api.context import whitelist
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.metadata import permission_layers
from grunt.metadata.registry import doctype_registry
from grunt.permissions.audit import diff, summary
lazy from grunt.document.api import documents


async def _definition(doctype: str) -> Any:
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return meta.doc


@whitelist(perm="grunt.manage_permissions")
async def app_rules_diff(doctype: str) -> dict[str, Any]:
    """How *doctype*'s rules on this site differ from its app's:
    ``{customized, outdated, changes, summary}`` - ``added`` are the site's own
    rules, ``removed`` the app's that the site doesn't have."""
    dt = await _definition(doctype)
    base = permission_layers.dump(dt.permissions_base) or []
    site = permission_layers.dump(dt.permissions) or []
    changes = diff("DocType", {"permissions": base}, {"permissions": site})
    return {
        "customized": permission_layers.customized(dt),
        "outdated": dt.permissions_outdated,
        "changes": changes,
        "summary": summary(changes),
    }


@whitelist(perm="grunt.manage_permissions")
async def restore_app_rules(doctype: str) -> dict[str, Any]:
    """Put the app's rules back on *doctype* - saved like any edit of the
    DocType (its write permission, the Permission Log)."""
    dt = await _definition(doctype)
    if dt.permissions_base is None:
        throw(_("The app's rules for this document type are not known"), "VALIDATION_ERROR")
    rules = permission_layers.dump(dt.permissions_base) or []
    await documents.save_doc("DocType", doctype, {"permissions": rules})
    return await app_rules_diff(doctype)
