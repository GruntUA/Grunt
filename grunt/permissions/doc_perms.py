"""What the current user may do with one document - sent to the form as ``__perms``.

The same checks the write paths enforce (role rows, row-level ``match``, User
Permissions, DocShare grants), evaluated up front so the UI hides actions the
server would refuse instead of letting the user edit and then answering 403.
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt.local import require_user
from grunt.permissions.rbac import permission_checker

PERMS_KEY = "__perms"
_ACTIONS = ("write", "delete", "create")


async def doc_permissions(doctype: str, doc: dict[str, Any]) -> dict[str, bool]:
    dt = await grunt.get_meta(doctype)
    if dt is None:
        return dict.fromkeys(_ACTIONS, False)
    user = require_user()
    perms = {}
    for action in _ACTIONS:
        # create is DocType-level: duplicating this document makes a new one.
        target = None if action == "create" else doc
        perms[action] = await permission_checker.check(user, dt, action, target)
    return perms


async def with_permissions(doctype: str, doc: Any) -> Any:
    """*doc* (an API response dict) with ``__perms`` added."""
    if isinstance(doc, dict):
        doc[PERMS_KEY] = await doc_permissions(doctype, doc)
    return doc
