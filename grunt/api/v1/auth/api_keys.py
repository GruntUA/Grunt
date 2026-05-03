"""API Key management endpoints.

POST   /api/v1/auth/api-keys          — create a new key (returns secret once)
GET    /api/v1/auth/api-keys          — list current user's keys (no secrets)
DELETE /api/v1/auth/api-keys/{key_id} — revoke a key
PATCH  /api/v1/auth/api-keys/{key_id} — update label / is_active / expires_at
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from grunt.api.router import GruntRouter
from grunt.api.v1.schemas.response import ok
from grunt.app import grunt
from grunt.auth.api_key_service import generate_api_key
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.User import User

if TYPE_CHECKING:
    from datetime import datetime

router = GruntRouter(prefix="/api-keys", tags=["auth", "api-keys"])


class CreateApiKeyRequest(BaseModel):
    label: str
    expires_at: datetime | None = None
    allowed_ips: str | None = None


class UpdateApiKeyRequest(BaseModel):
    label: str | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    allowed_ips: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Create a new API key for the current user.

    The full key is returned **once** — store it securely.
    Subsequent requests will only show the prefix.

    Example response::

        {
          "success": true,
          "data": {
            "id": "...",
            "key": "grnt_a1b2c3d4...",   ← shown once, never again
            "key_prefix": "a1b2c3d4",
            "label": "My CI key",
            "expires_at": null
          }
        }
    """
    if not body.label.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="label є обов'язковим")

    full_key, key_prefix, key_hash = generate_api_key()

    doc = await grunt.new_doc(
        "ApiKey",
        {
            "label": body.label.strip(),
            "user_id": user.id,
            "key_prefix": key_prefix,
            "key_hash": key_hash,
            "is_active": True,
            "expires_at": body.expires_at,
            "allowed_ips": body.allowed_ips or "",
        },
    )

    return ok(
        {
            "id": doc["id"],
            "key": full_key,
            "key_prefix": key_prefix,
            "label": doc["label"],
            "expires_at": doc.get("expires_at"),
            "allowed_ips": doc.get("allowed_ips") or "",
        }
    )


@router.get("")
async def list_api_keys(
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """List all API keys for the current user (secrets are never returned)."""
    filters: dict[str, Any] = {"user_id": user.id}
    if not user.is_superadmin:
        # Non-superadmins can only see their own keys
        filters["user_id"] = user.id

    keys = await grunt.get_list(
        "ApiKey",
        filters=filters,
        fields=[
            "id",
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
    return ok(keys)


@router.patch("/{key_id}")
async def update_api_key(
    key_id: str,
    body: UpdateApiKeyRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Update label, active state, or expiry of a key."""
    key_doc = await grunt.get_doc("ApiKey", key_id)
    _require_key_owner(key_doc, user)

    updates: dict[str, Any] = {}
    if body.label is not None:
        if not body.label.strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, detail="label не може бути порожнім"
            )
        updates["label"] = body.label.strip()
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.expires_at is not None:
        updates["expires_at"] = body.expires_at
    if body.allowed_ips is not None:
        updates["allowed_ips"] = body.allowed_ips

    if not updates:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Немає полів для оновлення"
        )

    doc = await grunt.save_doc("ApiKey", key_id, updates)
    return ok(
        {
            "id": doc["id"],
            "label": doc["label"],
            "key_prefix": doc["key_prefix"],
            "is_active": doc["is_active"],
            "expires_at": doc.get("expires_at"),
            "allowed_ips": doc.get("allowed_ips") or "",
        }
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(current_user),
) -> None:
    """Permanently revoke (delete) an API key."""
    key_doc = await grunt.get_doc("ApiKey", key_id)
    _require_key_owner(key_doc, user)
    await grunt.delete_doc("ApiKey", key_id)


def _require_key_owner(key_doc: dict[str, Any], user: User) -> None:
    """Raise 403 if user doesn't own the key and isn't a superadmin."""
    if not user.is_superadmin and key_doc.get("user_id") != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Немає доступу до цього ключа")
