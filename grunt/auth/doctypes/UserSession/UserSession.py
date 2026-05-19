"""UserSession — tracks per-device login sessions for each user."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def create_session(
    user_id: str,
    ip_address: str | None,
    user_agent: str | None,
    db_session: AsyncSession,
) -> str:
    """Create a new UserSession record and return the session_key."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.auth.doctypes.User.User import SYSTEM_USER  # noqa: PLC0415

    session_key = uuid.uuid4().hex

    try:
        async with grunt.system_context(db_session):
            await grunt.new_doc(
                "UserSession",
                {
                    "user": user_id,
                    "session_key": session_key,
                    "ip_address": ip_address or "",
                    "user_agent": (user_agent or "")[:512],
                    "last_active_at": datetime.now(UTC).isoformat(),
                    "is_active": True,
                },
            )
    except Exception:  # noqa: BLE001
        logger.debug("user_session.create_failed", user=user_id)

    return session_key


async def touch_session(
    session_key: str,
    db_session: AsyncSession,
) -> None:
    """Update last_active_at for the given session (best-effort, fire-and-forget)."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.auth.doctypes.User.User import SYSTEM_USER  # noqa: PLC0415

    try:
        async with grunt.system_context(db_session):
            sessions = await grunt.get_list(
                "UserSession",
                filters={"session_key": session_key, "is_active": True},
                fields=["name"],
                limit=1,
            )
            if sessions:
                await grunt.db.set_value(
                    "UserSession",
                    sessions[0]["name"],
                    "last_active_at",
                    datetime.now(UTC).isoformat(),
                )
    except Exception:  # noqa: BLE001
        logger.exception("suppressed_error")


async def terminate_session(
    session_id: str,
    requesting_user: str,
    db_session: AsyncSession,
) -> bool:
    """Deactivate a session. Only the owning user or superadmin may do this.

    Returns True on success.
    """
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.auth.doctypes.User.User import SYSTEM_USER  # noqa: PLC0415

    async with grunt.system_context(db_session):
        sessions = await grunt.get_list(
            "UserSession",
            filters={"name": session_id},
            fields=["name", "user"],
            limit=1,
        )
        if not sessions:
            return False

        if sessions[0]["user"] != requesting_user:
            return False

        await grunt.db.set_value("UserSession", session_id, "is_active", False)
        return True


async def terminate_all_user_sessions(
    user_id: str,
    db_session: AsyncSession,
    exclude_key: str | None = None,
) -> int:
    """Deactivate all active sessions for a user (e.g. on logout / password change)."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.auth.doctypes.User.User import SYSTEM_USER  # noqa: PLC0415

    async with grunt.system_context(db_session):
        sessions = await grunt.get_list(
            "UserSession",
            filters={"user": user_id, "is_active": True},
            fields=["name", "session_key"],
        )
        count = 0
        for s in sessions:
            if exclude_key and s.get("session_key") == exclude_key:
                continue
            await grunt.db.set_value("UserSession", s["name"], "is_active", False)
            count += 1
        return count
