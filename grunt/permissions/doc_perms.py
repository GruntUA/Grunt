"""What the current user may do with one document - sent to the form as ``__perms``.

The same checks the write paths enforce (role rows, row-level ``match``, User
Permissions, DocShare grants), evaluated up front so the UI hides actions the
server would refuse instead of letting the user edit and then answering 403.
"""

from typing import Any

from grunt.local import require_session_user
from grunt.metadata.registry import doctype_registry
from grunt.permissions.rbac import permission_checker

PERMS_KEY = "__perms"
_ACTIONS = ("write", "delete", "create", "print", "share")


async def doc_permissions(doctype: str, doc: dict[str, Any]) -> dict[str, bool]:
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        return dict.fromkeys(_ACTIONS, False)
    user = require_session_user()
    perms = {}
    for action in _ACTIONS:
        # create is DocType-level: duplicating this document makes a new one.
        target = None if action == "create" else doc
        if action == "share":
            perms[action] = await permission_checker.can_share(dt, doc, user=user)
        else:
            perms[action] = await permission_checker.check(dt, action, target, user=user)
    return perms


async def with_permissions(doctype: str, doc: Any) -> Any:
    """*doc* (an API response dict) with ``__perms`` added."""
    if isinstance(doc, dict):
        doc[PERMS_KEY] = await doc_permissions(doctype, doc)
    return doc
