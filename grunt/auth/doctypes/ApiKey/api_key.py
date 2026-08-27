"""ApiKey DocType controller and whitelisted API key methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt.auth.api_key_service import generate_api_key
from grunt.document.base import Document
from grunt.errors import forbidden

if TYPE_CHECKING:
    from datetime import datetime

    from grunt.auth.doctypes.User.user import User


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


@grunt.whitelist()
async def create_api_key(
    label: str,
    expires_at: datetime | None = None,
    allowed_ips: str | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """Create a new API key for the current user.

    The full key is returned once; subsequent reads return only key_prefix.
    """
    user = user or await grunt.get_current_user()
    clean_label = label.strip()
    if not clean_label:
        grunt.throw("label є обов'язковим", "VALIDATION")

    assert user.id is not None
    full_key, key_prefix, key_hash = generate_api_key()

    doc = await grunt.new_doc(
        "ApiKey",
        {
            "label": clean_label,
            "user_id": user.id,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "is_active": True,
            "expires_at": expires_at,
            "allowed_ips": allowed_ips or "",
        },
    )

    return {
        "name": doc["name"],
        "key": full_key,
        "key_prefix": key_prefix,
        "label": doc["label"],
        "expires_at": doc.get("expires_at"),
        "allowed_ips": doc.get("allowed_ips") or "",
    }


@grunt.whitelist()
async def list_api_keys(user: User | None = None) -> list[dict[str, Any]]:
    """List API keys (secrets are never returned)."""
    user = user or await grunt.get_current_user()

    filters: dict[str, Any] = {}
    if not user.is_superadmin:
        filters["user_id"] = user.id

    return await grunt.get_list(
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


@grunt.whitelist()
async def update_api_key(
    key_id: str,
    label: str | None = None,
    is_active: bool | None = None,
    expires_at: datetime | None = None,
    allowed_ips: str | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """Update label, active state, allowed IPs, or expiry of a key."""
    user = user or await grunt.get_current_user()
    key_doc = await grunt.get_doc("ApiKey", key_id)
    _require_key_owner(key_doc, user)

    updates: dict[str, Any] = {}
    if label is not None:
        clean_label = label.strip()
        if not clean_label:
            grunt.throw("label не може бути порожнім", "VALIDATION")
        updates["label"] = clean_label
    if is_active is not None:
        updates["is_active"] = is_active
    if expires_at is not None:
        updates["expires_at"] = expires_at
    if allowed_ips is not None:
        updates["allowed_ips"] = allowed_ips

    if not updates:
        grunt.throw("Немає полів для оновлення", "VALIDATION")

    doc = await grunt.save_doc("ApiKey", key_id, updates)
    return {
        "name": doc["name"],
        "label": doc["label"],
        "key_prefix": doc["key_prefix"],
        "is_active": doc["is_active"],
        "expires_at": doc.get("expires_at"),
        "allowed_ips": doc.get("allowed_ips") or "",
    }


@grunt.whitelist()
async def revoke_api_key(key_id: str, user: User | None = None) -> bool:
    """Permanently revoke (delete) an API key."""
    user = user or await grunt.get_current_user()
    key_doc = await grunt.get_doc("ApiKey", key_id)
    _require_key_owner(key_doc, user)
    await grunt.delete_doc("ApiKey", key_id)
    return True


def _require_key_owner(key_doc: dict[str, Any], user: User) -> None:
    """Raise 403 if user doesn't own the key and isn't a superadmin."""
    if not user.is_superadmin and key_doc.get("user_id") != user.id:
        raise forbidden("Немає доступу до цього ключа")
