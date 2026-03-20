"""Role-based access control."""
from __future__ import annotations

from typing import Literal, TYPE_CHECKING

from fastapi import HTTPException, status
import structlog

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()


class PermissionChecker:
    async def check(
        self,
        user: "GruntUser",
        doctype: "DocType",
        action: Literal["read", "write", "create", "delete", "submit"],
        doc: dict | None = None,
    ) -> bool:
        if getattr(user, "is_superadmin", False):
            return True

        if not doctype.permissions:
            return True  # No permissions defined = open (dev mode)

        user_roles = set(getattr(user, "roles", []) or [])

        for perm in doctype.permissions:
            role = perm.role if hasattr(perm, "role") else perm.get("role", "")
            if role not in user_roles and role != "All":
                continue
            perm_val = (
                getattr(perm, action, False)
                if hasattr(perm, action)
                else perm.get(action, False)
            )
            if not perm_val:
                continue
            # Check match expression
            match_expr = (
                perm.match if hasattr(perm, "match") else perm.get("match")
            )
            if match_expr and doc:
                if not self._eval_match(match_expr, user, doc):
                    continue
            return True

        return False

    async def require(
        self,
        user: "GruntUser",
        doctype: "DocType",
        action: Literal["read", "write", "create", "delete", "submit"],
        doc: dict | None = None,
    ) -> None:
        allowed = await self.check(user, doctype, action, doc)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Недостатньо прав",
                        "details": [],
                    },
                },
            )

    def _eval_match(self, match_expr: str, user: "GruntUser", doc: dict) -> bool:
        safe_globals: dict = {"__builtins__": {}}
        safe_locals: dict = {
            "user": user.email,
            "owner": doc.get("owner"),
            "doc": doc,
        }
        try:
            return bool(eval(match_expr, safe_globals, safe_locals))  # noqa: S307
        except Exception:  # noqa: BLE001
            return True


permission_checker = PermissionChecker()
