"""WebAuthnCredential DocType controller + passkey self-management endpoints.

The register / authenticate ceremonies live in
:class:`grunt.auth.providers.webauthn.WebAuthnProvider` (driven through
``/api/v1/auth/webauthn/...``). What is left here is the CRUD a signed-in user
needs to *manage* the passkeys they already have.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import grunt
from grunt.document.base import Document
from grunt.log import log


class WebAuthnCredential(Document):
    """Controller for WebAuthnCredential.

    Rows are created by the WebAuthn provider after a verified attestation —
    never through the generic form — so there is no create-time validation to
    do here beyond what the metadata enforces.
    """

    user: str
    label: str | None
    credential_id: str
    public_key: str
    sign_count: int
    aaguid: str | None
    transports: str | None
    backed_up: bool
    last_used_at: datetime | None


def _row_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row["name"],
        "label": row.get("label") or "Passkey",
        "last_used_at": row.get("last_used_at"),
        "backed_up": bool(row.get("backed_up")),
        "transports": [t for t in (row.get("transports") or "").split(",") if t],
        "created_at": row.get("creation"),
    }


async def _owned_passkey(name: str, user_id: str) -> str:
    """Return the passkey id if it belongs to *user_id*, else raise 404."""
    rows = await grunt.get_list(
        "WebAuthnCredential",
        filters={"name": name, "user": user_id},
        fields=["name"],
        limit=1,
    )
    if not rows:
        grunt.throw("Passkey not found", "NOT_FOUND")
    return rows[0]["name"]


@grunt.whitelist()
async def list_my_passkeys() -> list[dict[str, Any]]:
    """Passkeys registered by the current user."""
    current = await grunt.get_current_user()
    rows = await grunt.get_list(
        "WebAuthnCredential",
        filters={"user": current.id},
        fields=["name", "label", "last_used_at", "backed_up", "transports", "creation"],
        order_by="creation desc",
        limit=100,
    )
    return [_row_view(r) for r in rows]


@grunt.whitelist()
async def rename_passkey(name: str, label: str) -> bool:
    """Rename one of the current user's passkeys."""
    current = await grunt.get_current_user()
    assert current.id is not None
    label = (label or "").strip()
    if not label:
        grunt.throw("Label is required", "VALIDATION_ERROR")
    await grunt.set_value(
        "WebAuthnCredential", await _owned_passkey(name, current.id), "label", label
    )
    return True


@grunt.whitelist()
async def delete_passkey(name: str) -> bool:
    """Remove one of the current user's passkeys."""
    current = await grunt.get_current_user()
    assert current.id is not None
    target = await _owned_passkey(name, current.id)
    await grunt.delete_doc("WebAuthnCredential", target)
    log.info("webauthn.passkey_removed", user=current.email, credential=target)
    return True


@grunt.whitelist()
async def touch_passkey(name: str) -> bool:
    """Update ``last_used_at`` (used by the frontend after a successful ceremony)."""
    current = await grunt.get_current_user()
    assert current.id is not None
    await grunt.set_value(
        "WebAuthnCredential",
        await _owned_passkey(name, current.id),
        "last_used_at",
        datetime.now(UTC),
    )
    return True
