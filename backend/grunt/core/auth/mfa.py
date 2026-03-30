"""MFA / TOTP service for Grunt.

Provides Time-based One-Time Password (TOTP) setup and verification,
backed by the ``mfa_secret`` and ``mfa_backup_codes`` fields on the User DocType.

Requires the ``mfa`` optional extras::

    uv pip install grunt[mfa]
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.service import _user_table

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()

_APP_NAME = "Grunt"
_BACKUP_CODE_COUNT = 8


def _require_pyotp():
    try:
        import pyotp  # noqa: PLC0415
        return pyotp
    except ImportError as exc:
        raise HTTPException(
            501,
            detail="MFA requires the 'mfa' extras: uv pip install grunt[mfa]",
        ) from exc


# ── Setup ─────────────────────────────────────────────────────────────────────


def generate_mfa_secret() -> str:
    """Generate a new random TOTP secret (base32 encoded)."""
    pyotp = _require_pyotp()
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """Return the otpauth:// URI for QR code generation."""
    pyotp = _require_pyotp()
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_APP_NAME)


def get_qr_code_svg(secret: str, email: str) -> str:
    """Return an SVG string of the QR code for the given TOTP URI.

    Falls back to a plain URI string if the ``qrcode`` library is not installed.
    """
    uri = get_totp_uri(secret, email)
    try:
        import qrcode  # noqa: PLC0415
        import qrcode.image.svg  # noqa: PLC0415

        factory = qrcode.image.svg.SvgImage
        qr = qrcode.make(uri, image_factory=factory)
        buf = io.BytesIO()
        qr.save(buf)
        return buf.getvalue().decode("utf-8")
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
    pyotp = _require_pyotp()
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


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


async def begin_mfa_setup(user: "GruntUser", session: AsyncSession) -> dict:
    """Generate a new TOTP secret, store it (unconfirmed), and return setup info.

    The secret is saved immediately but ``mfa_enabled`` stays ``False`` until
    :func:`confirm_mfa_setup` is called with a valid TOTP code.

    Returns::

        {
            "secret": "BASE32SECRET",
            "qr_svg": "<svg>...</svg>",   # or otpauth:// URI if qrcode not installed
        }
    """
    secret = generate_mfa_secret()
    table = _user_table()
    await session.execute(
        update(table)
        .where(table.c.id == user.id)
        .values(mfa_secret=secret, mfa_enabled=False)
    )
    await session.flush()
    logger.info("mfa.setup_started", user=user.email)
    return {
        "secret": secret,
        "qr_svg": get_qr_code_svg(secret, user.email),
    }


async def confirm_mfa_setup(
    user: "GruntUser",
    code: str,
    session: AsyncSession,
) -> list[str]:
    """Verify the TOTP code and activate MFA for the user.

    Returns a list of plain-text backup codes that the user should save.
    Raises HTTP 422 if the code is wrong or no secret is pending.
    """
    # Load current secret
    table = _user_table()
    row = (
        await session.execute(
            select(table.c.mfa_secret).where(table.c.id == user.id)
        )
    ).first()
    if not row or not row[0]:
        raise HTTPException(422, detail="MFA не налаштовано. Спочатку запустіть setup.")

    secret = row[0]
    if not verify_totp(secret, code):
        raise HTTPException(422, detail="Невірний TOTP код")

    backup_codes = _generate_backup_codes()
    backup_hashes = [_hash_backup_code(c) for c in backup_codes]

    await session.execute(
        update(table)
        .where(table.c.id == user.id)
        .values(
            mfa_enabled=True,
            mfa_secret=secret,
            mfa_backup_codes=json.dumps(backup_hashes),
        )
    )
    await session.flush()
    logger.info("mfa.enabled", user=user.email)
    return backup_codes


async def disable_mfa(user: "GruntUser", session: AsyncSession) -> None:
    """Disable MFA and clear stored secrets for the user."""
    table = _user_table()
    await session.execute(
        update(table)
        .where(table.c.id == user.id)
        .values(mfa_enabled=False, mfa_secret="", mfa_backup_codes=None)
    )
    await session.flush()
    logger.info("mfa.disabled", user=user.email)


async def check_mfa_code(
    user: "GruntUser",
    code: str,
    session: AsyncSession,
) -> None:
    """Verify TOTP or backup code for the user.

    Raises HTTP 401 on failure. Consumes a backup code if used (updates DB).
    """
    table = _user_table()
    row = (
        await session.execute(
            select(table.c.mfa_secret, table.c.mfa_backup_codes)
            .where(table.c.id == user.id)
        )
    ).first()

    if not row or not row[0]:
        raise HTTPException(401, detail="MFA не налаштовано")

    secret, backup_json = row[0], row[1]

    # Try TOTP first
    if verify_totp(secret, code):
        return

    # Try backup code
    backup_hashes: list[str] = json.loads(backup_json) if backup_json else []
    matched, remaining = verify_backup_code(backup_hashes, code)
    if matched:
        await session.execute(
            update(table)
            .where(table.c.id == user.id)
            .values(mfa_backup_codes=json.dumps(remaining))
        )
        await session.flush()
        logger.info("mfa.backup_code_used", user=user.email, remaining=len(remaining))
        return

    raise HTTPException(401, detail="Невірний код MFA")
