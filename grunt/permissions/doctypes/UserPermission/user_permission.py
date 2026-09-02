"""UserPermission DocType controller — record-level access restrictions.

A ``UserPermission`` row means: *user* may only touch documents linked (via a
Link field) to *for_value* of DocType *allow*. Multiple rows for the same
``allow`` widen the allowed set (OR); different ``allow`` types narrow it (AND).

Enforcement lives in :mod:`grunt.permissions.user_permissions`, wired into
``apply_permission_filter`` (lists / counts / link search / reports) and
``PermissionChecker.check`` (single-document read / write / delete).
"""

from __future__ import annotations

import grunt
from grunt.document.base import Document


class UserPermission(Document):
    """DocType controller for UserPermission.

    NB: the "who" field is ``for_user`` (not ``user``) — ``user`` is a
    reserved attribute on ``Document`` (the acting user).
    """

    for_user: str
    allow: str
    for_value: str
    apply_to_all_doctypes: bool
    applicable_for: str | None
    is_default: bool

    async def validate(self) -> None:
        if not self.apply_to_all_doctypes and not self.applicable_for:
            raise ValueError(
                "Вкажіть «Лише для документа» або увімкніть «Застосувати до всіх документів»"
            )
        if self.apply_to_all_doctypes:
            self.applicable_for = None

        dupes = await grunt.get_list(
            "UserPermission",
            filters={
                "for_user": self.for_user,
                "allow": self.allow,
                "for_value": self.for_value,
                "applicable_for": self.applicable_for,
            },
            fields=["name"],
            limit=2,
        )
        if any(r["name"] != self.name for r in dupes):
            raise ValueError("Такий дозвіл користувача вже існує")

    async def after_save(self) -> None:
        _invalidate(self.for_user)

    async def after_delete(self) -> None:
        _invalidate(self.for_user)


def _invalidate(user_id: str | None) -> None:
    from grunt.permissions.user_permissions import invalidate_user_permission_cache

    invalidate_user_permission_cache(user_id)
