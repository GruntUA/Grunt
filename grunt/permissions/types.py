"""Shared permission type aliases.

Single source of truth for the permission-action literals used across the
RBAC checker, the request guards, and the facade - so the literal set is not
repeated (and stays in sync) at every call site.
"""

from __future__ import annotations

from typing import Literal

# Every permission action understood by the RBAC checker.
#
# "select" is a narrow read: it authorises resolving / searching a DocType's
# *identifier* columns (name, title_field, search_fields) for a Link-field
# picker, without granting list access, full-document read, or field
# unmasking. Any role with "read" implicitly has "select" too.
PermissionAction = Literal["read", "write", "create", "delete", "submit", "select"]

# Mutating actions only - the subset accepted by write-side guards.
WriteAction = Literal["create", "write", "delete", "submit"]
