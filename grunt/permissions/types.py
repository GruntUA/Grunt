"""Shared permission type aliases.

Single source of truth for the permission-action literals used across the
RBAC checker, the request guards, and the facade — so the literal set is not
repeated (and stays in sync) at every call site.
"""

from __future__ import annotations

from typing import Literal

# Every permission action understood by the RBAC checker.
PermissionAction = Literal["read", "write", "create", "delete", "submit"]

# Mutating actions only — the subset accepted by write-side guards.
WriteAction = Literal["create", "write", "delete", "submit"]
