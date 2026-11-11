"""Shared permission type aliases.

Single source of truth for the permission-action literals used across the
RBAC checker, the request guards, and the facade - so the literal set is not
repeated (and stays in sync) at every call site.
"""

from typing import Literal

# Every permission action understood by the RBAC checker.
#
# "select" is a narrow read: it authorises resolving / searching a DocType's
# *identifier* columns (name, title_field, search_fields) for a Link-field
# picker, without granting list access, full-document read, or field
# unmasking. Any role with "read" implicitly has "select" too.
#
# "export" / "import" / "print" / "share" / "report" take data out of (or bulk
# into) the system - granted separately from read/write; "share" also needs the
# level it hands out (read or write) - see ``grunt.metadata.permission.ACTIONS``.
PermissionAction = Literal[
    "read",
    "write",
    "create",
    "delete",
    "select",
    "export",
    "import",
    "print",
    "share",
    "report",
]

# Mutating actions only - the subset accepted by write-side guards.
WriteAction = Literal["create", "write", "delete"]
