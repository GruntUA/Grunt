"""Sign-in policy beyond the password itself (FRAPPE_GAP_PLAN #20).

Checked by :func:`grunt.auth.login.issue_login` (every sign-in path ends there)
and by the password endpoints:

* **password expiry** - ``SystemSettings.password_max_age_days``: signing in
  with a password older than that returns a ``password_change_required``
  challenge instead of tokens; ``change_expired_password_api`` sets a new one
  and goes on with the sign-in. A user with no ``password_changed_at`` yet
  (from before this) starts the clock at that sign-in - nobody is forced to
  change right after an update;
* **sign-in hours** - ``User.login_after`` / ``login_before`` in the site's
  time zone (a range across midnight works);
* **per-user IP addresses** - ``User.allowed_ips``, on top of the role's limit
  (:mod:`grunt.auth.ip_policy`);
* **sessions per user** - ``SystemSettings.max_sessions_per_user``: a new
  session ends the oldest past the limit;
* **SSO only** - ``SystemSettings.disable_password_login``: password sign-in is
  refused for everyone but administrators (who could otherwise lock everyone
  out when the identity provider is down).
"""

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from grunt.config import settings
from grunt.db.api import GruntDB
from grunt.local import require_session, system_context
from grunt.site.settings import get_setting
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.auth.ip_policy import ip_allowed, parse_ip_list
lazy from grunt.permissions.perms import ALL, user_perms

_db = GruntDB()  # stateless: reads through the context's session


async def _site_now() -> datetime:
    tz = await get_setting("timezone") or settings.default_timezone
    try:
        return datetime.now(ZoneInfo(str(tz)))
    except Exception:  # noqa: BLE001 - an unknown zone name falls back to the default
        return datetime.now(ZoneInfo(settings.default_timezone))


def _as_time(value: Any) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except ValueError:
        return None


async def within_login_hours(user: User) -> bool:
    """Whether now (site time) is inside the user's ``login_after`` -
    ``login_before``; an open end is no limit."""
    start, end = _as_time(user.data.get("login_after")), _as_time(user.data.get("login_before"))
    if start is None and end is None:
        return True
    now = (await _site_now()).time().replace(tzinfo=None)
    if start is not None and end is not None and start > end:  # across midnight
        return now >= start or now < end
    return (start is None or now >= start) and (end is None or now < end)


def login_hours(user: User) -> tuple[str, str]:
    """The user's sign-in hours as ``HH:MM`` (empty for an open end) - for the message."""
    return tuple(  # type: ignore[return-value]
        t.strftime("%H:%M") if (t := _as_time(user.data.get(key))) else ""
        for key in ("login_after", "login_before")
    )


def user_ip_allowed(user: User, client_ip: str | None) -> bool:
    """``User.allowed_ips`` - none set is no limit; the role's limit is separate."""
    allowed = parse_ip_list(user.data.get("allowed_ips"))
    return not allowed or ip_allowed(client_ip, allowed)


async def password_expired(user: User) -> bool:
    """The user's password is older than ``password_max_age_days``. A user
    without ``password_changed_at`` gets it set now (the clock starts) and
    isn't expired; a user without a password (SSO, email link) never is."""
    max_age = int(await get_setting("password_max_age_days", 0) or 0)
    if max_age <= 0 or not user.data.get("hashed_password"):
        return False
    changed = user.data.get("password_changed_at")
    if not changed:
        await mark_password_changed(str(user.id))
        return False
    if isinstance(changed, str):
        changed = datetime.fromisoformat(changed)
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=UTC)
    return (datetime.now(UTC) - changed).days >= max_age


async def mark_password_changed(user_id: str) -> None:
    """Stamp ``password_changed_at`` - every place that sets a password calls it."""
    async with system_context(require_session()):
        await _db.set_value("User", user_id, "password_changed_at", datetime.now(UTC))


async def password_login_allowed(user: User) -> bool:
    """SSO only (``disable_password_login``) refuses password sign-in, but not
    for administrators (every permission) - the way back in when SSO fails."""
    if not await get_setting("disable_password_login", False):
        return True
    return ALL in await user_perms(user.email)


async def enforce_session_limit(user_id: str, keep_sid: str) -> int:
    """End the user's oldest active sessions past ``max_sessions_per_user``
    (never *keep_sid*, the one just opened). Returns how many were ended."""
    limit = int(await get_setting("max_sessions_per_user", 0) or 0)
    if limit <= 0:
        return 0
    async with system_context(require_session()):
        rows = await _db.get_all(
            "UserSession",
            filters={"user": user_id, "is_active": True},
            fields=["name"],
            order_by="last_active_at",
            order="desc",
            limit=None,
        )
        others = [r["name"] for r in rows if r["name"] != keep_sid]
        ended = others[max(0, limit - 1) :]
        for sid in ended:
            await _db.set_value("UserSession", sid, "is_active", False)
    return len(ended)
