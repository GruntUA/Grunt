"""The browser's session: the UserSession refresh token in an HttpOnly cookie.

Script on the page never sees the refresh token - the SPA keeps only the
short-lived access token, in memory, and gets a new one from ``refresh_api``,
which reads this cookie. ``Path=/`` sends it to the public site too, so a site
page can tell who is reading it.

The API itself authenticates by the ``Authorization`` header only; the cookie
is accepted by the session endpoints alone (refresh, logout), and those check
``Origin`` on top of ``SameSite=Lax`` against cross-site requests - and by
read-only GET methods that opt in (``@grunt.whitelist(session_cookie=True)``).

Next to it goes ``grunt_signed_in=1``, readable by script and holding no
secret: a cached public page decides between «Sign in» and «Go to the app»
with it without asking the server.
"""

from urllib.parse import urlsplit

from fastapi import Request, Response

from grunt.config import settings
lazy from grunt.auth.doctypes.User.user import User, get_auth_context_user
lazy from grunt.auth.doctypes.UserSession.user_session import session_user
lazy from grunt.auth.service import session_ttl_minutes

SESSION_COOKIE = "grunt_session"
SIGNED_IN_COOKIE = "grunt_signed_in"


def _secure() -> bool:
    return settings.app_url.startswith("https://")


async def set_session_cookie(response: Response, refresh_token: str) -> None:
    """Hand the browser its session; it lives as long as the idle timeout."""

    max_age = await session_ttl_minutes() * 60
    response.set_cookie(
        SESSION_COOKIE,
        refresh_token,
        max_age=max_age,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(),
    )
    response.set_cookie(
        SIGNED_IN_COOKIE, "1", max_age=max_age, path="/", samesite="lax", secure=_secure()
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=_secure()
    )
    response.delete_cookie(SIGNED_IN_COOKIE, path="/", samesite="lax", secure=_secure())


def session_token(request: Request | None) -> str | None:
    """The refresh token the browser sent, if any."""
    if request is None:
        return None
    return request.cookies.get(SESSION_COOKIE) or None


def same_origin(request: Request | None) -> bool:
    """Whether a cookie-authenticated request comes from this site's own pages.

    A browser always sends ``Origin`` on a cross-site POST; its absence means a
    same-origin request from an older browser or a non-browser client.
    """

    if request is None:
        return True
    origin = request.headers.get("origin")
    if not origin:
        return True
    # Host names only: a proxy's ``Host $host`` drops the port the Origin keeps.
    host = urlsplit(f"//{request.headers.get('host', '')}").hostname
    return urlsplit(origin).hostname == host


async def cookie_user(request: Request | None) -> User | None:
    """Who the session cookie belongs to - the session active and not idle, the
    account enabled. Read only: the session is not rotated or touched. Needs a
    grunt context (a DB session)."""

    token = session_token(request)
    if not token:
        return None
    uid = await session_user(token)
    if uid is None:
        return None
    user = await get_auth_context_user(uid)
    return user if user is not None and user.is_active else None
