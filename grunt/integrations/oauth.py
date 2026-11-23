"""OAuth 2.0 on behalf of a document: a :class:`ConnectedApp` (the client
registered at Google / Microsoft / another provider) grants a token to one
document - an ``EmailAccount`` signs in to SMTP/IMAP with it (XOAUTH2).

Flow:

1. :func:`authorize` - the form asks for the provider's consent page. The
   caller must be allowed to *write* the document; the scopes come from the
   document's controller (``oauth_scopes(provider)``) plus the app's own.
2. :func:`callback` - the provider sends the browser back with a code; the
   signed ``state`` says which app and document it is for. The code becomes
   an :class:`OAuthToken` row (one per app + document); the controller's
   ``on_oauth_connected(account)`` may note the account on the document.
3. :func:`get_access_token` - a valid access token for the document, refreshed
   with the refresh token when it is (about to be) expired.

The redirect URI to register at the provider is
``https://<site>/api/v1/method/grunt.integrations.oauth.callback``.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict
from urllib.parse import urlencode

import httpx2
from fastapi import Request
from fastapi.responses import RedirectResponse

from grunt.api.context import whitelist
from grunt.config import settings
from grunt.db.api import GruntDB
from grunt.errors import ApplicationError, unprocessable
from grunt.i18n import _
from grunt.local import require_session, system_context, user_email
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.permissions.guards import doc_guard
from grunt.utils.http import public_base_url
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

CALLBACK = "/api/v1/method/grunt.integrations.oauth.callback"
STATE_TTL_SECONDS = 15 * 60
#: Refresh this long before the access token runs out.
EXPIRY_MARGIN = timedelta(seconds=120)
_TIMEOUT = httpx2.Timeout(20.0)

MASK = "••••••••"
#: ``ConnectedApp`` / ``OAuthToken`` fields that never leave the server.
SECRET_FIELDS = ("client_secret", "access_token", "refresh_token")


class OAuthError(ApplicationError):
    """The provider refused (or could not be asked for) a token."""


@dataclass(frozen=True)
class Endpoints:
    authorize_url: str
    token_url: str
    #: Scopes every grant of this provider asks for (who signed in, offline use).
    base_scopes: tuple[str, ...] = ()
    extra_params: dict[str, str] = field(default_factory=dict)


def endpoints(app: dict[str, Any]) -> Endpoints:
    """Where *app* (a ``ConnectedApp`` row) sends the browser and gets tokens."""
    provider = app.get("provider") or "Other"
    if provider == "Google":
        return Endpoints(
            "https://accounts.google.com/o/oauth2/v2/auth",
            "https://oauth2.googleapis.com/token",
            ("openid", "email"),
            # A refresh token is handed out only for offline access, and only
            # on a consent screen - ask for it on every connect.
            {"access_type": "offline", "prompt": "consent"},
        )
    if provider == "Microsoft":
        tenant = (app.get("tenant") or "").strip() or "common"
        base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
        return Endpoints(
            f"{base}/authorize",
            f"{base}/token",
            ("openid", "email", "offline_access"),
            {"prompt": "select_account"},
        )
    return Endpoints(app.get("authorization_url") or "", app.get("token_url") or "")


def redirect_uri(request: Request | None) -> str:
    return public_base_url(request) + CALLBACK


def split_scopes(value: str | None) -> list[str]:
    return [s for s in (value or "").replace(",", " ").split() if s]


def _merge_scopes(*groups: Any) -> str:
    seen: dict[str, None] = {}
    for group in groups:
        for scope in group or ():
            seen.setdefault(scope, None)
    return " ".join(seen)


# State: which app and document, who started, until when - signed so the
# callback (a guest request) can't be pointed at another document.


def _sign(payload: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), f"connected-app:{payload}".encode(), hashlib.sha256
    ).hexdigest()


def make_state(app: str, doctype: str, name: str, user: str, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + STATE_TTL_SECONDS)
    raw = json.dumps([app, doctype, name, user, exp]).encode()
    payload = base64.urlsafe_b64encode(raw).decode()
    return f"{payload}.{_sign(payload)}"


def read_state(state: str) -> tuple[str, str, str, str]:
    """``(app, doctype, name, user)`` of a valid unexpired state; ValueError otherwise."""
    payload, _sep, sig = (state or "").partition(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        raise ValueError("bad signature")
    app, doctype, name, user, exp = json.loads(base64.urlsafe_b64decode(payload))
    if exp < time.time():
        raise ValueError("expired")
    return app, doctype, name, user


# Rows


async def load_app(name: str) -> dict[str, Any]:
    """The ``ConnectedApp`` row with its real secret."""
    row = await _db.get_value("ConnectedApp", name, "*")
    if not row:
        raise OAuthError(_("Connected app “%(name)s” not found") % {"name": name})
    return dict(row)


async def find_token(doctype: str, name: str) -> dict[str, Any] | None:
    """The ``OAuthToken`` row of *doctype* / *name* (with its secrets), if any."""
    rows = await _db.get_all(
        "OAuthToken",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["*"],
        limit=1,
    )
    return dict(rows[0]) if rows else None


def _expires_at(data: dict[str, Any]) -> datetime:
    seconds = data.get("expires_in")
    return datetime.now(UTC) + timedelta(seconds=int(3600 if seconds in (None, "") else seconds))


def _id_token_email(id_token: str | None) -> str:
    """The signed-in account from the token response's ``id_token``.

    Not verified: it came straight from the provider's token endpoint over
    TLS, in exchange for our client secret (OIDC Core 3.1.3.7) - and it only
    labels the connection, it grants nothing.
    """
    try:
        payload = (id_token or "").split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except IndexError, ValueError:
        return ""
    return str(claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "")


async def _token_request(app: dict[str, Any], data: dict[str, str]) -> dict[str, Any]:
    """POST to the app's token endpoint; the JSON answer or :class:`OAuthError`."""
    url = endpoints(app).token_url
    if not url:
        raise OAuthError(_("The token URL of the connected app is not set"))
    try:
        async with httpx2.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                url,
                data={
                    **data,
                    "client_id": app.get("client_id") or "",
                    "client_secret": app.get("client_secret") or "",
                },
                headers={"Accept": "application/json"},
            )
        body = response.json()
    except (httpx2.HTTPError, ValueError) as exc:
        raise OAuthError(str(exc)) from exc
    if response.status_code >= 400 or "access_token" not in body:
        message = body.get("error_description") or body.get("error") or response.text
        raise OAuthError(str(message)[:500], code=str(body.get("error") or "ERROR"))
    return body


async def save_token(
    app: dict[str, Any], doctype: str, name: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Store a token response for *doctype* / *name*; the saved values."""
    existing = await find_token(doctype, name)
    values: dict[str, Any] = {
        "access_token": data["access_token"],
        "expires_at": _expires_at(data),
        "scopes": data.get("scope") or (existing or {}).get("scopes"),
        "last_error": None,
    }
    # A refresh answer may leave the refresh token out - keep the old one then.
    if data.get("refresh_token"):
        values["refresh_token"] = data["refresh_token"]
    account = _id_token_email(data.get("id_token"))
    if account:
        values["account"] = account
    if existing:
        if existing.get("connected_app") != app["name"]:
            values["connected_app"] = app["name"]
        await _db.set_value("OAuthToken", existing["name"], values)
        return {**existing, **values}
    values |= {
        "connected_app": app["name"],
        "reference_doctype": doctype,
        "reference_name": name,
        "connected_at": datetime.now(UTC),
    }
    doc = await documents.new_doc("OAuthToken", values)
    return {**values, "name": doc["name"]}


# Access tokens

_locks: dict[str, asyncio.Lock] = {}


def _fresh(row: dict[str, Any]) -> bool:
    expires = row.get("expires_at")
    if not row.get("access_token") or not expires:
        return False
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires - EXPIRY_MARGIN > datetime.now(UTC)


async def get_access_token(doctype: str, name: str) -> str:
    """A valid access token for *doctype* / *name*; :class:`OAuthError` without one.

    An expired token is refreshed and the new one saved - and **committed**, so
    call this outside a transaction you mean to roll back (the mail worker
    commits before talking to SMTP/IMAP anyway). A refused refresh (revoked
    consent, changed password) is noted on the token: the account has to be
    connected again.
    """
    key = f"{doctype}:{name}"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        row = await find_token(doctype, name)
        if row is None:
            raise OAuthError(_("The account is not connected: click “Connect account”"))
        if _fresh(row):
            return row["access_token"]
        if not row.get("refresh_token"):
            raise OAuthError(_("The connection has expired: connect the account again"))
        app = await load_app(row["connected_app"])
        try:
            data = await _token_request(
                app, {"grant_type": "refresh_token", "refresh_token": row["refresh_token"]}
            )
        except OAuthError as exc:
            log.warning("oauth.refresh_failed", reference=key, error=str(exc))
            await _db.set_value("OAuthToken", row["name"], "last_error", str(exc))
            await require_session().commit()
            raise OAuthError(
                _("The provider refused to renew access (%(error)s): connect the account again")
                % {"error": exc}
            ) from exc
        saved = await save_token(app, doctype, name, data)
        await require_session().commit()
        log.info("oauth.token_refreshed", reference=key)
        return saved["access_token"]


async def disconnect_reference(doctype: str, name: str) -> None:
    """Forget the token of *doctype* / *name* (the provider's grant stays -
    revoke it in the account's security settings)."""
    row = await find_token(doctype, name)
    if row:
        await documents.delete_doc("OAuthToken", row["name"], ignore_permissions=True)


async def _controller_hook(doctype: str, name: str, method: str, *args: Any) -> Any:
    doc = await documents.get_doc_instance(doctype, name)
    hook = getattr(doc, method, None)
    return await hook(*args) if hook else None


# RPC


class AuthorizeLink(TypedDict):
    #: The provider's consent page to open.
    url: str
    #: Where the provider sends the user back (must match the app's settings).
    redirect_uri: str


class ConnectionStatus(TypedDict):
    connected: bool
    account: str
    connected_app: str
    connected_at: str
    error: str


@whitelist()
async def authorize(
    connected_app: str, doctype: str, name: str, request: Request | None = None
) -> AuthorizeLink:
    """The provider's consent page that connects *doctype* / *name* through *connected_app*."""
    await doc_guard(doctype, name, "write")
    async with system_context():
        try:
            app = await load_app(connected_app)
        except OAuthError as exc:
            raise unprocessable(str(exc)) from exc
        if not app.get("enabled", True):
            raise unprocessable(_("The connected app is disabled"))
        if not app.get("client_id") or not app.get("client_secret"):
            raise unprocessable(_("Enter the Client ID and secret of the connected app first"))
        wanted = await _controller_hook(doctype, name, "oauth_scopes", app.get("provider"))
    ends = endpoints(app)
    if not ends.authorize_url:
        raise unprocessable(_("The authorization URL of the connected app is not set"))
    params = {
        "client_id": app["client_id"],
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "state": make_state(connected_app, doctype, name, user_email() or ""),
        "scope": _merge_scopes(ends.base_scopes, wanted, split_scopes(app.get("scopes"))),
        **ends.extra_params,
    }
    return {
        "url": f"{ends.authorize_url}?{urlencode(params)}",
        "redirect_uri": params["redirect_uri"],
    }


async def _back_to_form(
    doctype: str, name: str, outcome: str, message: str = ""
) -> RedirectResponse:
    query = urlencode({"oauth": outcome, **({"message": message} if message else {})})
    meta = await doctype_registry.get_meta(doctype)
    dt = meta.doc if meta else None
    app = getattr(dt, "app", None) or getattr(dt, "module", None) or "grunt"
    path = f"/app/{app}/{doctype}/{name}" if meta else "/app"
    return RedirectResponse(f"{path}?{query}", status_code=303)


@whitelist(allow_guest=True)
async def callback(
    state: str = "",
    code: str = "",
    error: str = "",
    error_description: str = "",
    request: Request | None = None,
) -> RedirectResponse:
    """The provider sends the browser back here with a code (or an error)."""
    try:
        app_name, doctype, name, _user = read_state(state)
    except (ValueError, TypeError) as exc:
        raise unprocessable(_("The sign-in link is invalid or expired")) from exc
    if error or not code:
        return await _back_to_form(
            doctype, name, "error", error_description or error or _("No code returned")
        )
    async with system_context():
        try:
            app = await load_app(app_name)
            data = await _token_request(
                app,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri(request),
                },
            )
            if not data.get("refresh_token"):
                raise OAuthError(
                    _("The provider gave no refresh token: allow offline access and try again")
                )
            saved = await save_token(app, doctype, name, data)
            await _controller_hook(doctype, name, "on_oauth_connected", saved.get("account") or "")
        except OAuthError as exc:
            return await _back_to_form(doctype, name, "error", str(exc)[:300])
        await require_session().commit()
    log.info("oauth.connected", app=app_name, reference=f"{doctype}:{name}")
    return await _back_to_form(doctype, name, "ok")


@whitelist()
async def status(doctype: str, name: str) -> ConnectionStatus:
    """Whether *doctype* / *name* holds a token - for the form, no secrets."""
    await doc_guard(doctype, name, "read")
    row = await find_token(doctype, name)
    if not row:
        return {
            "connected": False,
            "account": "",
            "connected_app": "",
            "connected_at": "",
            "error": "",
        }
    at = row.get("connected_at")
    return {
        "connected": True,
        "account": row.get("account") or "",
        "connected_app": row.get("connected_app") or "",
        "connected_at": at.isoformat() if isinstance(at, datetime) else str(at or ""),
        "error": row.get("last_error") or "",
    }


@whitelist()
async def disconnect(doctype: str, name: str) -> bool:
    """Forget the token of *doctype* / *name*."""
    await doc_guard(doctype, name, "write")
    async with system_context():
        await disconnect_reference(doctype, name)
        await _controller_hook(doctype, name, "on_oauth_connected", "")
    return True


# Hooks


def _mask(row: Any) -> None:
    if isinstance(row, dict):
        for key in SECRET_FIELDS:
            if row.get(key):
                row[key] = MASK


async def mask_secrets(**kwargs: Any) -> None:
    """``after_read`` of ``ConnectedApp`` / ``OAuthToken``: no secret leaves the server."""
    _mask(kwargs.get("doc"))
    data = kwargs.get("data")
    for row in data if isinstance(data, list) else [data]:
        _mask(row)
