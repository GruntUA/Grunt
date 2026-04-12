"""API Key service — generation and verification of static API keys.

Key format: ``grnt_<64 hex chars>``
  - first 8 chars after prefix = key_prefix (stored in DB, used for lookup)
  - full 64 chars = key_secret (hashed with SHA-256, shown to user once)

Security notes:
  - SHA-256 is appropriate here because the key is a high-entropy random token
    (64 hex chars = 256 bits of entropy). bcrypt would be wasteful.
  - The key_prefix is public and allows O(1) DB lookup without scanning all keys.
"""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.core.doctypes.user.user import GruntUser

logger = structlog.get_logger()

_KEY_PREFIX = "grnt_"
_KEY_BYTES = 32  # 64 hex chars


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key triple.

    Returns:
        (full_key, key_prefix, key_hash)
        - full_key:   shown to the user once, never stored
        - key_prefix: first 8 hex chars, stored in DB for lookup
        - key_hash:   SHA-256 of full_key, stored in DB for verification
    """
    raw = secrets.token_hex(_KEY_BYTES)  # 64 hex chars
    full_key = f"{_KEY_PREFIX}{raw}"
    key_prefix = raw[:8]
    key_hash = _hash_key(full_key)
    return full_key, key_prefix, key_hash


def _hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def verify_key(full_key: str, stored_hash: str) -> bool:
    """Return True if full_key matches the stored SHA-256 hash."""
    return secrets.compare_digest(_hash_key(full_key), stored_hash)


async def authenticate_api_key(
    full_key: str,
    session: AsyncSession,
    client_ip: str | None = None,
) -> GruntUser | None:
    """Authenticate a request using an API key string.

    Returns the associated GruntUser on success, None on failure.
    Updates ``last_used_at`` in the background (best-effort).
    """
    if not full_key.startswith(_KEY_PREFIX):
        return None

    raw = full_key[len(_KEY_PREFIX):]
    if len(raw) != _KEY_BYTES * 2:
        return None

    key_prefix = raw[:8]

    from grunt.app import grunt  # noqa: PLC0415
    from grunt.core.doctypes.user.user import SYSTEM_USER, get_user_by_id  # noqa: PLC0415

    _tokens = grunt.set_context(session, None, SYSTEM_USER)
    try:
        rows = await grunt.db.get_all(
            "ApiKey",
            filters={"key_prefix": key_prefix, "is_active": True},
            fields=["id", "key_hash", "user_id", "expires_at", "allowed_ips"],
            limit=5,
        )
    finally:
        grunt.reset_context(_tokens)

    if not rows:
        return None

    # Find matching key (there should only be one per prefix, but check all)
    matched_row = None
    for row in rows:
        stored_hash = row.get("key_hash") or ""
        if verify_key(full_key, stored_hash):
            matched_row = row
            break

    if not matched_row:
        logger.warning("api_key.invalid_secret", prefix=key_prefix)
        return None

    # Check expiry
    expires_at = matched_row.get("expires_at")
    if expires_at:
        exp = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(str(expires_at))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < datetime.now(UTC):
            logger.info("api_key.expired", prefix=key_prefix)
            return None

    # Check IP allowlist
    allowed_ips_raw = (matched_row.get("allowed_ips") or "").strip()
    if allowed_ips_raw and client_ip:
        allowed = {ip.strip() for ip in allowed_ips_raw.split(",") if ip.strip()}
        if not _ip_allowed(client_ip, allowed):
            logger.warning("api_key.ip_rejected", prefix=key_prefix, ip=client_ip)
            return None

    # Load user
    user = await get_user_by_id(matched_row["user_id"], session)
    if user is None or not user.is_active:
        return None

    # Update last_used_at (best-effort, don't fail the request)
    try:
        _tokens = grunt.set_context(session, None, SYSTEM_USER)
        try:
            await grunt.db.set_value("ApiKey", matched_row["id"], "last_used_at", datetime.now(UTC))
        finally:
            grunt.reset_context(_tokens)
    except Exception:  # noqa: BLE001
        pass

    logger.info("api_key.authenticated", prefix=key_prefix, user=user.email)
    return user


def _ip_allowed(client_ip: str, allowed: set[str]) -> bool:
    """Check if client_ip is in the allowed set (supports CIDR notation)."""
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False
