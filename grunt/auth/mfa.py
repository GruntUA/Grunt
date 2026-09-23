"""MFA / TOTP service for Grunt.

Provides Time-based One-Time Password (TOTP) setup and verification,
backed by the ``mfa_secret`` and ``mfa_backup_codes`` fields on the User DocType.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from typing import TYPE_CHECKING

import pyotp
from fastapi import HTTPException

from grunt.app import grunt as grunt_app
from grunt.log import log

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


_APP_NAME = "Grunt"
_BACKUP_CODE_COUNT = 8


# ── Setup ─────────────────────────────────────────────────────────────────────


def generate_mfa_secret() -> str:
    """Generate a new random TOTP secret (base32 encoded)."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Return the otpauth:// URI for QR code generation."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_APP_NAME)


def get_qr_code_svg(secret: str, email: str) -> str:
    """Return an SVG string of the QR code for the given TOTP URI.

    Falls back to a plain URI string if the ``qrcode`` library is not installed.
    """
    uri = get_totp_uri(secret, email)
    try:
        import qrcode
        import qrcode.image.svg

        factory = qrcode.image.svg.SvgPathImage
        qr = qrcode.make(uri, image_factory=factory)
        buf = io.BytesIO()
        qr.save(buf)
        svg = buf.getvalue().decode("utf-8").strip()
        if svg.startswith("<?xml"):
            svg = svg[svg.find("?>") + 2 :].strip()
        # Remove fixed width/height so CSS can scale it
        import re

        svg = re.sub(r'width="[^"]+"', 'width="100%"', svg, count=1)
        svg = re.sub(r'height="[^"]+"', 'height="100%"', svg, count=1)
        return svg
    except ImportError:
        # qrcode not installed — return the raw URI so the frontend can render it
        return uri


def _generate_backup_codes() -> list[str]:
    """Generate a set of one-time backup codes (hex strings)."""
    return [os.urandom(5).hex().upper() for _ in range(_BACKUP_CODE_COUNT)]


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# ── Verification ──────────────────────────────────────────────────────────────


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against the given secret.

    Allows a 1-step window (30s before/after) to handle clock drift.
    """
    totp = pyotp.TOTP(secret.strip())
    return totp.verify(code.strip(), valid_window=1)


def verify_backup_code(stored_hashes: list[str], code: str) -> tuple[bool, list[str]]:
    """Check if the given code matches any stored backup code hash.

    Returns ``(matched, remaining_hashes)`` — the matched hash is removed.
    """
    code_hash = _hash_backup_code(code.upper())
    if code_hash in stored_hashes:
        remaining = [h for h in stored_hashes if h != code_hash]
        return True, remaining
    return False, stored_hashes


# ── DB operations ─────────────────────────────────────────────────────────────


async def mfa_setup_required(user: User) -> bool:
    """True if MFA is off but one of the user's roles has ``Role.require_mfa``."""
    if user.mfa_enabled:
        return False
    roles = list(getattr(user, "roles", None) or [])
    if not roles:
        return False
    enforcing = await grunt_app.db.get_all(
        "Role", filters={"name__in": roles, "require_mfa": True}, pluck="name", limit=1
    )
    return bool(enforcing)


async def begin_mfa_setup(user: User) -> dict:
    """Generate a new TOTP secret, store it (unconfirmed), and return setup info."""
    # Prevent overwriting if already enabled
    if user.mfa_enabled:
        raise HTTPException(
            400, detail="MFA вже увімкнено. Спочатку вимкніть його, щоб переналаштувати."
        )

    secret = generate_mfa_secret()
    await grunt_app.db.set_value("User", user.id, {"mfa_secret": secret, "mfa_enabled": False})
    log.info("mfa.setup_started", user=user.email)
    return {
        "secret": secret,
        "qr_svg": get_qr_code_svg(secret, user.email),
    }


async def confirm_mfa_setup(user: User, code: str) -> list[str]:
    """Verify the TOTP code and activate MFA for the user.

    Returns a list of plain-text backup codes that the user should save.
    Raises HTTP 422 if the code is wrong or no secret is pending.
    """
    rows = await grunt_app.db.get_all(
        "User", filters={"name": user.id}, fields=["mfa_secret"], limit=1
    )
    if not rows or not rows[0].get("mfa_secret"):
        raise HTTPException(422, detail="MFA не налаштовано. Спочатку запустіть setup.")

    secret = rows[0]["mfa_secret"]
    if not verify_totp(secret, code):
        raise HTTPException(422, detail="Невірний TOTP код")

    backup_codes = _generate_backup_codes()
    backup_hashes = [_hash_backup_code(c) for c in backup_codes]
    await grunt_app.db.set_value(
        "User",
        user.id,
        {
            "mfa_enabled": True,
            "mfa_secret": secret,
            "mfa_backup_codes": json.dumps(backup_hashes),
        },
    )
    log.info("mfa.enabled", user=user.email)
    return backup_codes


async def disable_mfa(user: User) -> None:
    """Disable MFA and clear stored secrets for the user."""
    await grunt_app.db.set_value(
        "User",
        user.id,
        {
            "mfa_enabled": False,
            "mfa_secret": "",
            "mfa_backup_codes": None,
        },
    )
    log.info("mfa.disabled", user=user.email)


async def check_mfa_code(user: User, code: str, session: object | None = None) -> None:
    """Verify TOTP or backup code for the user.

    Raises HTTP 401 on failure. Consumes a backup code if used (updates DB).

    *session* — pass the SQLAlchemy session only when called from a pre-auth
    context (e.g. ``/auth/mfa-login``) where the grunt request context is not
    yet active.  Omit when called from a GruntRouter endpoint where the context
    is already set by middleware.
    """
    import contextlib

    if session is not None:
        from grunt.site.manager import site_manager

        eng = site_manager.get_engine(site_manager.get_active_site())
        ctx = grunt_app.system_context(session, eng)
    else:
        ctx = contextlib.nullcontext()

    async with ctx:
        rows = await grunt_app.db.get_all(
            "User",
            filters={"name": user.id},
            fields=["mfa_secret", "mfa_backup_codes"],
            limit=1,
        )
        if not rows or not rows[0].get("mfa_secret"):
            raise HTTPException(401, detail="MFA не налаштовано")

        row = rows[0]
        secret = row["mfa_secret"]
        backup_json = row.get("mfa_backup_codes")

        # Try TOTP first
        if verify_totp(secret, code):
            return

        # Try backup code
        backup_hashes: list[str] = json.loads(backup_json) if backup_json else []
        matched, remaining = verify_backup_code(backup_hashes, code)
        if matched:
            await grunt_app.db.set_value(
                "User", user.id, {"mfa_backup_codes": json.dumps(remaining)}
            )
            log.info("mfa.backup_code_used", user=user.email, remaining=len(remaining))
            return

        raise HTTPException(401, detail="Невірний код MFA")
