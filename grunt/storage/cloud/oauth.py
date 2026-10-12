"""Connecting a ``StorageRemote`` to Google Drive / Dropbox / OneDrive.

Two ways to get an OAuth token:

* **paste** (no app registration): ``rclone authorize "drive"`` on any
  computer with a browser prints a token made with rclone's own client id;
  :func:`set_token` stores it. ``client_id`` stays empty, so rclone keeps
  using its own id to refresh it.
* **own app**: with ``client_id`` / ``client_secret`` of an app registered
  at the provider, :func:`authorize` sends the browser to the provider and
  :func:`callback` exchanges the code. The app's redirect URI is
  ``https://<site>/api/v1/method/grunt.storage.cloud.oauth.callback``.

The token is kept in rclone's format (``access_token``, ``refresh_token``,
``expiry``); rclone refreshes it and :class:`~grunt.storage.cloud.rclone.Rclone`
writes the new one back.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx2
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

import grunt
from grunt import _, log, whitelist
from grunt.config import settings
from grunt.storage.cloud import load_remote
from grunt.storage.cloud.providers import get_provider
from grunt.storage.cloud.rclone import RemoteError
from grunt.utils.http import public_base_url

CALLBACK = "/api/v1/method/grunt.storage.cloud.oauth.callback"
STATE_TTL_SECONDS = 15 * 60
_TIMEOUT = httpx2.Timeout(20.0)


def redirect_uri(request: Request | None) -> str:
    return public_base_url(request) + CALLBACK


# State: which remote, who started, until when - signed so the callback
# (a guest request) can't be pointed at another remote.


def _sign(payload: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), f"cloud-oauth:{payload}".encode(), hashlib.sha256
    ).hexdigest()


def make_state(remote: str, user: str, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + STATE_TTL_SECONDS)
    payload = base64.urlsafe_b64encode(json.dumps([remote, user, exp]).encode()).decode()
    return f"{payload}.{_sign(payload)}"


def read_state(state: str) -> tuple[str, str]:
    """``(remote, user)`` of a valid unexpired state; ValueError otherwise."""
    payload, _sep, sig = state.partition(".")
    if not hmac.compare_digest(sig, _sign(payload)):
        raise ValueError("bad signature")
    remote, user, exp = json.loads(base64.urlsafe_b64decode(payload))
    if exp < time.time():
        raise ValueError("expired")
    return remote, user


# Tokens


def rclone_token(data: dict[str, Any]) -> str:
    """A provider's token response as rclone's ``token`` value."""
    expiry = datetime.now(UTC) + timedelta(seconds=int(data.get("expires_in") or 3600))
    return json.dumps(
        {
            "access_token": data["access_token"],
            "token_type": data.get("token_type") or "Bearer",
            "refresh_token": data.get("refresh_token") or "",
            "expiry": expiry.isoformat().replace("+00:00", "Z"),
        }
    )


def parse_pasted_token(text: str) -> dict[str, Any]:
    """The JSON object in what ``rclone authorize`` printed (arrows and all)."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        token = json.loads(match.group(0)) if match else None
    except ValueError:
        token = None
    if not isinstance(token, dict) or not token.get("access_token"):
        raise RemoteError(
            _("This is not an rclone token: paste the whole {…} line printed by rclone authorize")
        )
    return token


async def _describe_account(provider: str, access_token: str) -> tuple[str, dict[str, Any]]:
    """Best-effort account label + extra rclone options (OneDrive's drive id)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx2.AsyncClient(timeout=_TIMEOUT) as client:
            if provider == "Google Drive":
                r = await client.get(
                    "https://www.googleapis.com/drive/v3/about",
                    params={"fields": "user(emailAddress,displayName)"},
                    headers=headers,
                )
                user = r.json().get("user") or {}
                return user.get("emailAddress") or user.get("displayName") or "", {}
            if provider == "Dropbox":
                r = await client.post(
                    "https://api.dropboxapi.com/2/users/get_current_account", headers=headers
                )
                return r.json().get("email") or "", {}
            if provider == "OneDrive":
                r = await client.get("https://graph.microsoft.com/v1.0/me/drive", headers=headers)
                drive = r.json()
                owner = (drive.get("owner") or {}).get("user") or {}
                extra = {"drive_id": drive.get("id", ""), "drive_type": drive.get("driveType", "")}
                return owner.get("displayName") or owner.get("email") or "", extra
    except (httpx2.HTTPError, ValueError) as exc:
        log.warning("cloud.oauth_account_failed", provider=provider, error=str(exc))
    return "", {}


async def save_token(remote: dict[str, Any], token: str) -> str:
    """Store *token* (rclone JSON) on *remote*; returns the account label."""
    access = json.loads(token).get("access_token") or ""
    account, extra = await _describe_account(remote.get("provider") or "", access)
    if remote.get("provider") == "OneDrive" and not extra.get("drive_id"):
        raise RemoteError(_("Could not read the OneDrive drive of this account"))
    await grunt.db.set_value(
        "StorageRemote",
        remote["name"],
        {
            "oauth_token": token,
            "oauth_extra": json.dumps(extra) if extra else None,
            "oauth_account": account or _("connected"),
            "oauth_connected_at": datetime.now(UTC),
        },
    )
    return account


# RPC


@whitelist(roles=["System Manager"])
async def set_token(name: str, token: str) -> dict[str, Any]:
    """Store a token pasted from ``rclone authorize``."""
    remote = await load_remote(name)
    try:
        parsed = parse_pasted_token(token)
        account = await save_token(remote, json.dumps(parsed))
    except RemoteError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"account": account}


@whitelist(roles=["System Manager"])
async def authorize(name: str, request: Request | None = None) -> dict[str, str]:
    """The provider's sign-in URL for *name* (needs its own client id/secret)."""
    remote = await load_remote(name)
    endpoints = get_provider(remote.get("provider")).oauth
    if endpoints is None:
        raise HTTPException(400, _("This storage type does not sign in through a browser"))
    if not remote.get("client_id") or not remote.get("client_secret"):
        raise HTTPException(400, _("Enter the Client ID and secret of your app and save first"))
    params = {
        "client_id": remote["client_id"],
        "redirect_uri": redirect_uri(request),
        "response_type": "code",
        "state": make_state(name, grunt.get_user().email),
        **endpoints.extra_params,
    }
    if endpoints.scope:
        params["scope"] = endpoints.scope
    return {
        "url": f"{endpoints.authorize_url}?{urlencode(params)}",
        "redirect_uri": params["redirect_uri"],
    }


def _back_to_form(name: str, outcome: str, message: str = "") -> RedirectResponse:
    query = urlencode({"cloud_auth": outcome, **({"message": message} if message else {})})
    return RedirectResponse(f"/app/grunt/StorageRemote/{name}?{query}", status_code=303)


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
        name, _user = read_state(state)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, _("The sign-in link is invalid or expired")) from exc
    if error or not code:
        return _back_to_form(name, "error", error_description or error or _("No code returned"))
    async with grunt.system_context(grunt.get_session()):
        remote = await load_remote(name)
        endpoints = get_provider(remote.get("provider")).oauth
        if endpoints is None:
            raise HTTPException(400, _("This storage type does not sign in through a browser"))
        try:
            async with httpx2.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    endpoints.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri(request),
                        "client_id": remote["client_id"],
                        "client_secret": remote["client_secret"],
                    },
                    headers={"Accept": "application/json"},
                )
            data = response.json()
            if response.status_code >= 400 or "access_token" not in data:
                message = data.get("error_description") or data.get("error") or response.text
                return _back_to_form(name, "error", str(message)[:300])
            await save_token(remote, rclone_token(data))
        except (httpx2.HTTPError, ValueError, RemoteError) as exc:
            return _back_to_form(name, "error", str(exc)[:300])
        await grunt.get_session().commit()
    return _back_to_form(name, "ok")
