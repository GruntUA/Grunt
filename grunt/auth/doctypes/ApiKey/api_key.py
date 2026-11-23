"""ApiKey DocType controller and whitelisted API key methods."""

from datetime import datetime
from typing import Any

from grunt.api.context import whitelist
from grunt.auth.api_key_service import generate_api_key
from grunt.auth.current import acting_user
from grunt.document.base import Document
from grunt.errors import forbidden, throw
from grunt.i18n import _
from grunt.permissions.perms import has_perm
from grunt.permissions.roles import get_roles
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.document.api import documents


class ApiKey(Document):
    """DocType controller for API keys."""

    label: str
    user_id: str
    key_prefix: str
    key_hash: str
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    allowed_ips: str | None
    read_only: bool | None
    roles: list[dict[str, Any]] | None

    async def validate(self) -> None:
        """A key acts with some of its user's roles, never others - one the
        user doesn't hold would hand the key more than the user has."""
        wanted = [str(r["role_name"]) for r in self.roles or [] if r.get("role_name")]
        if not wanted:
            return
        held = set(await get_roles(await self._user_email()))
        foreign = sorted({r for r in wanted if r not in held})
        if foreign:
            throw(
                _("The key's user doesn't hold these roles: %(roles)s")
                % {"roles": ", ".join(foreign)},
                "VALIDATION_ERROR",
            )

    async def _user_email(self) -> str:
        email = await self.grunt.db.get_value("User", self.user_id, "email")
        return str(email or self.user_id)


@whitelist()
async def create_api_key(
    label: str,
    expires_at: datetime | None = None,
    allowed_ips: str | None = None,
    read_only: bool = False,
    roles: list[str] | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """Create a new API key for the current user.

    The full key is returned once; subsequent reads return only key_prefix.
    """
    user = user or acting_user()
    clean_label = label.strip()
    if not clean_label:
        throw(_("Label is required"), "VALIDATION")

    assert user.id is not None
    full_key, key_prefix, key_hash = generate_api_key()

    doc = await documents.new_doc(
        "ApiKey",
        {
            "label": clean_label,
            "user_id": user.id,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "is_active": True,
            "expires_at": expires_at,
            "allowed_ips": allowed_ips or "",
            "read_only": read_only,
            "roles": [{"role_name": r} for r in roles or []],
        },
    )

    return {
        "name": doc.name,
        "key": full_key,
        "key_prefix": key_prefix,
        "label": doc.label,
        "expires_at": doc.expires_at,
        "allowed_ips": doc.allowed_ips or "",
    }


@whitelist()
async def list_api_keys(user: User | None = None) -> list[dict[str, Any]]:
    """List API keys (secrets are never returned)."""
    user = user or acting_user()

    filters: dict[str, Any] = {}
    if not await has_perm("grunt.manage_users", user=user.email):
        filters["user_id"] = user.id

    return await documents.get_list(
        "ApiKey",
        filters=filters,
        fields=[
            "name",
            "label",
            "key_prefix",
            "is_active",
            "last_used_at",
            "expires_at",
            "allowed_ips",
        ],
        order_by="created_at",
        order="desc",
        limit=200,
    )


@whitelist()
async def update_api_key(
    key_id: str,
    label: str | None = None,
    is_active: bool | None = None,
    expires_at: datetime | None = None,
    allowed_ips: str | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """Update label, active state, allowed IPs, or expiry of a key."""
    user = user or acting_user()
    key_doc = await documents.get_doc(ApiKey, key_id)
    await _require_key_owner(key_doc, user)

    updates: dict[str, Any] = {}
    if label is not None:
        clean_label = label.strip()
        if not clean_label:
            throw(_("label cannot be empty"), "VALIDATION")
        updates["label"] = clean_label
    if is_active is not None:
        updates["is_active"] = is_active
    if expires_at is not None:
        updates["expires_at"] = expires_at
    if allowed_ips is not None:
        updates["allowed_ips"] = allowed_ips

    if not updates:
        throw(_("No fields to update"), "VALIDATION")

    doc = await documents.save_doc("ApiKey", key_id, updates)
    return {
        "name": doc.name,
        "label": doc.label,
        "key_prefix": doc.key_prefix,
        "is_active": doc.is_active,
        "expires_at": doc.expires_at,
        "allowed_ips": doc.allowed_ips or "",
    }


@whitelist()
async def revoke_api_key(key_id: str, user: User | None = None) -> bool:
    """Permanently revoke (delete) an API key."""
    user = user or acting_user()
    key_doc = await documents.get_doc(ApiKey, key_id)
    await _require_key_owner(key_doc, user)
    await documents.delete_doc("ApiKey", key_id)
    return True


async def _require_key_owner(key_doc: ApiKey, user: User) -> None:
    """Raise 403 if user doesn't own the key and doesn't manage users."""
    if key_doc.user_id != user.id and not await has_perm("grunt.manage_users", user=user.email):
        raise forbidden(_("No access to this key"))
