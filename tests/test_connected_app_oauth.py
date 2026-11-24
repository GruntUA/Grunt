"""ConnectedApp + OAuthToken: a mailbox signs in to SMTP/IMAP through OAuth
(Gmail / Microsoft 365, XOAUTH2) - state, endpoints, the code exchange,
refreshing, secrets never handed out, the mail transports. No network: the
provider's token endpoint is replaced by a stub.
"""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from grunt.email import inbound
from grunt.email.inbound import pull_emails
from grunt.email.service import smtp_sign_in
from grunt.errors import ApplicationError
from grunt.integrations import oauth
from grunt.integrations.oauth import MASK, OAuthError, make_state, read_state
from grunt.metadata.doctype import DocType
from tests.support import check_as, make_user

BOX = "office@council.example.com"
ERRORS = (ApplicationError, HTTPException)


def _id_token(email: str) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"e30.{claims}.sig"


@pytest.fixture
async def mailbox(ctx):
    app = await ctx.new_doc(
        "ConnectedApp",
        {
            "title": "Council M365",
            "provider": "Microsoft",
            "tenant": "contoso.onmicrosoft.com",
            "client_id": "cid",
            "client_secret": "s3cret",
        },
    )
    account = await ctx.new_doc(
        "EmailAccount",
        {
            "email_address": BOX,
            "provider": "Microsoft 365",
            "auth_method": "OAuth",
            "connected_app": app["name"],
            "enable_outgoing": True,
        },
    )
    await ctx.db._session().commit()
    return account


@pytest.fixture
def token_endpoint(monkeypatch):
    """Replace the provider's token endpoint; ``calls`` - what it was asked."""
    calls: list[dict] = []
    answers: list[dict | Exception] = []

    async def fake(app, data):
        calls.append({"app": app["name"], **data})
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(oauth, "_token_request", fake)
    return calls, answers


# Pure helpers


def test_state_round_trip_tamper_and_expiry():
    state = make_state("app", "EmailAccount", "box-1", "admin@example.com")
    assert read_state(state) == ("app", "EmailAccount", "box-1", "admin@example.com")

    payload, _sep, sig = state.partition(".")
    forged = base64.urlsafe_b64encode(
        json.dumps(["app", "EmailAccount", "other", "x", int(time.time()) + 600]).encode()
    ).decode()
    with pytest.raises(ValueError):
        read_state(f"{forged}.{sig}")

    old = make_state("app", "EmailAccount", "box-1", "u", now=time.time() - 3600)
    with pytest.raises(ValueError):
        read_state(old)


def test_endpoints_per_provider():
    google = oauth.endpoints({"provider": "Google"})
    assert google.token_url == "https://oauth2.googleapis.com/token"
    assert google.extra_params["access_type"] == "offline"

    ms = oauth.endpoints({"provider": "Microsoft", "tenant": "contoso.onmicrosoft.com"})
    assert ms.authorize_url.startswith("https://login.microsoftonline.com/contoso.onmicrosoft.com/")
    assert "offline_access" in ms.base_scopes
    assert "/common/" in oauth.endpoints({"provider": "Microsoft", "tenant": " "}).token_url

    other = oauth.endpoints(
        {"provider": "Other", "authorization_url": "https://a", "token_url": "https://t"}
    )
    assert (other.authorize_url, other.token_url, other.base_scopes) == (
        "https://a",
        "https://t",
        (),
    )


def test_id_token_email():
    assert oauth._id_token_email(_id_token("me@example.com")) == "me@example.com"
    assert oauth._id_token_email("garbage") == ""
    assert oauth._id_token_email(None) == ""


# Documents


@pytest.mark.asyncio
async def test_secrets_are_masked_and_kept(ctx, mailbox):
    app = await ctx.get_doc("ConnectedApp", "Council M365")
    assert app["client_secret"] == MASK
    await ctx.save_doc("ConnectedApp", "Council M365", {"client_secret": MASK, "client_id": "c2"})
    stored = await ctx.db.get_value("ConnectedApp", "Council M365", "client_secret")
    assert stored == "s3cret"

    await oauth.save_token(
        await oauth.load_app("Council M365"),
        "EmailAccount",
        mailbox["name"],
        {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600},
    )
    token = await oauth.find_token("EmailAccount", mailbox["name"])
    assert token and token["access_token"] == "AT"  # the server itself reads them
    row = await ctx.get_doc("OAuthToken", token["name"])
    assert row.get("access_token") in (MASK, None) and row.get("refresh_token") in (MASK, None)
    listed = await ctx.get_list("OAuthToken", fields=["*"])
    assert all(r.get("access_token") in (MASK, None) for r in listed)


@pytest.mark.asyncio
async def test_other_provider_needs_https_endpoints(ctx):
    with pytest.raises(ERRORS):
        await ctx.new_doc(
            "ConnectedApp",
            {
                "title": "Own IdP",
                "provider": "Other",
                "client_id": "c",
                "client_secret": "s",
                "authorization_url": "http://id.example.com/auth",
                "token_url": "https://id.example.com/token",
            },
        )


@pytest.mark.asyncio
async def test_email_account_presets_and_oauth_needs_an_app(ctx, mailbox):
    assert mailbox["smtp_server"] == "smtp.office365.com"
    assert mailbox["imap_server"] == "outlook.office365.com"
    with pytest.raises(ERRORS):
        await ctx.new_doc(
            "EmailAccount",
            {"email_address": "x@council.example.com", "auth_method": "OAuth"},
        )


@pytest.mark.asyncio
async def test_tokens_are_only_looked_at_or_deleted():
    from pathlib import Path

    path = Path(oauth.__file__).parent / "doctypes/OAuthToken/OAuthToken.json"
    dt = DocType.model_validate(json.loads(path.read_text()))
    admin = make_user("admin@example.com", roles=["System Manager"])
    plain = make_user("plain@example.com")
    for action in ("read", "write", "create", "delete"):
        assert not await check_as(plain, dt, action)
        assert await check_as(admin, dt, action) is (action in ("read", "delete"))


# Connecting and refreshing


@pytest.mark.asyncio
async def test_authorize_asks_for_mail_scopes(ctx, mailbox):
    link = await oauth.authorize(
        connected_app="Council M365", doctype="EmailAccount", name=mailbox["name"]
    )
    query = parse_qs(urlparse(link["url"]).query)
    scopes = query["scope"][0].split()
    assert "https://outlook.office.com/SMTP.Send" in scopes
    assert "https://outlook.office.com/IMAP.AccessAsUser.All" in scopes
    assert "offline_access" in scopes
    assert query["client_id"] == ["cid"]
    assert read_state(query["state"][0])[:3] == ("Council M365", "EmailAccount", mailbox["name"])
    assert link["redirect_uri"].endswith(oauth.CALLBACK)


@pytest.mark.asyncio
async def test_callback_stores_token_and_notes_the_account(ctx, mailbox, token_endpoint):
    calls, answers = token_endpoint
    answers.append(
        {
            "access_token": "AT1",
            "refresh_token": "RT1",
            "expires_in": 3600,
            "id_token": _id_token(BOX),
        }
    )
    state = make_state("Council M365", "EmailAccount", mailbox["name"], "admin")
    response = await oauth.callback(state=state, code="the-code")
    assert response.status_code == 303
    assert "oauth=ok" in response.headers["location"]
    assert calls[0]["grant_type"] == "authorization_code" and calls[0]["code"] == "the-code"

    token = await oauth.find_token("EmailAccount", mailbox["name"])
    assert token and token["refresh_token"] == "RT1" and token["account"] == BOX
    assert await ctx.db.get_value("EmailAccount", mailbox["name"], "oauth_account") == BOX
    assert await oauth.get_access_token("EmailAccount", mailbox["name"]) == "AT1"
    assert len(calls) == 1  # still fresh - no refresh

    status = await oauth.status(doctype="EmailAccount", name=mailbox["name"])
    assert status["connected"] and status["account"] == BOX


@pytest.mark.asyncio
async def test_callback_with_provider_error_goes_back_to_the_form(ctx, mailbox):
    state = make_state("Council M365", "EmailAccount", mailbox["name"], "admin")
    response = await oauth.callback(state=state, error="access_denied")
    assert "oauth=error" in response.headers["location"]
    assert await oauth.find_token("EmailAccount", mailbox["name"]) is None


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_refresh_token_kept(ctx, mailbox, token_endpoint):
    calls, answers = token_endpoint
    app = await oauth.load_app("Council M365")
    await oauth.save_token(
        app,
        "EmailAccount",
        mailbox["name"],
        {"access_token": "OLD", "refresh_token": "RT", "expires_in": 60},  # inside the margin
    )
    answers.append({"access_token": "NEW", "expires_in": 3600})
    assert await oauth.get_access_token("EmailAccount", mailbox["name"]) == "NEW"
    assert calls[-1] == {
        "app": "Council M365",
        "grant_type": "refresh_token",
        "refresh_token": "RT",
    }
    token = await oauth.find_token("EmailAccount", mailbox["name"])
    assert token and token["refresh_token"] == "RT" and token["access_token"] == "NEW"


@pytest.mark.asyncio
async def test_refused_refresh_is_noted(ctx, mailbox, token_endpoint):
    _calls, answers = token_endpoint
    app = await oauth.load_app("Council M365")
    await oauth.save_token(
        app,
        "EmailAccount",
        mailbox["name"],
        {"access_token": "OLD", "refresh_token": "RT", "expires_in": 0},
    )
    answers.append(OAuthError("AADSTS70008: expired", code="invalid_grant"))
    with pytest.raises(OAuthError):
        await oauth.get_access_token("EmailAccount", mailbox["name"])
    token = await oauth.find_token("EmailAccount", mailbox["name"])
    assert token and "AADSTS70008" in (token["last_error"] or "")


@pytest.mark.asyncio
async def test_not_connected_and_disconnect(ctx, mailbox):
    with pytest.raises(OAuthError):
        await oauth.get_access_token("EmailAccount", mailbox["name"])
    await oauth.save_token(
        await oauth.load_app("Council M365"),
        "EmailAccount",
        mailbox["name"],
        {"access_token": "AT", "refresh_token": "RT"},
    )
    await ctx.db.set_value("EmailAccount", mailbox["name"], "oauth_account", BOX)
    await oauth.disconnect(doctype="EmailAccount", name=mailbox["name"])
    assert await oauth.find_token("EmailAccount", mailbox["name"]) is None
    assert not await ctx.db.get_value("EmailAccount", mailbox["name"], "oauth_account")


@pytest.mark.asyncio
async def test_deleting_the_mailbox_drops_its_token(ctx, mailbox):
    await oauth.save_token(
        await oauth.load_app("Council M365"),
        "EmailAccount",
        mailbox["name"],
        {"access_token": "AT", "refresh_token": "RT"},
    )
    await ctx.delete_doc("EmailAccount", mailbox["name"])
    assert await ctx.db.count("OAuthToken") == 0


# Mail transports


class FakeSmtp:
    def __init__(self):
        self.calls: list[tuple] = []

    async def auth_xoauth2(self, user, token):
        self.calls.append(("xoauth2", user, token))

    async def login(self, user, password):
        self.calls.append(("login", user, password))


@pytest.mark.asyncio
async def test_smtp_signs_in_with_xoauth2_as_the_granting_account(monkeypatch):
    async def token(account):
        return "AT"

    monkeypatch.setattr("grunt.email.service.oauth_token", token)
    smtp = FakeSmtp()
    account = {
        "name": "box",
        "auth_method": "OAuth",
        "email_address": "alias@council.example.com",
        "oauth_account": BOX,
    }
    await smtp_sign_in(smtp, account)  # type: ignore[arg-type]
    assert smtp.calls == [("xoauth2", BOX, "AT")]

    smtp = FakeSmtp()
    await smtp_sign_in(smtp, {"email_address": BOX, "smtp_password": "pw"})  # type: ignore[arg-type]
    assert smtp.calls == [("login", BOX, "pw")]


class _Response:
    def __init__(self, result="OK", lines=None):
        self.result = result
        self.lines = lines or []


class FakeImap:
    def __init__(self, *_args):
        self.signed_in: tuple | None = None

    async def wait_hello_from_server(self):
        return None

    async def xoauth2(self, user, token):
        self.signed_in = (user, token)
        return _Response()

    async def login(self, user, password):
        raise AssertionError("an OAuth mailbox must not log in with a password")

    async def select(self, _folder):
        return _Response("NO")

    async def logout(self):
        return None


@pytest.mark.asyncio
async def test_imap_signs_in_with_xoauth2(monkeypatch):
    imap = FakeImap()
    monkeypatch.setattr(inbound.aioimaplib, "IMAP4_SSL", lambda *a: imap)

    async def token(account):
        return "AT"

    monkeypatch.setattr(inbound, "oauth_token", token)
    account = {
        "name": "box",
        "enable_incoming": True,
        "imap_server": "outlook.office365.com",
        "email_address": BOX,
        "auth_method": "OAuth",
        "imap_folders": "INBOX",
    }
    emails, _state = await pull_emails(account)
    assert emails == [] and imap.signed_in == (BOX, "AT")


def test_fresh_margin():
    soon = datetime.now(UTC) + timedelta(seconds=30)
    later = datetime.now(UTC) + timedelta(hours=1)
    assert not oauth._fresh({"access_token": "a", "expires_at": soon})
    assert oauth._fresh({"access_token": "a", "expires_at": later.replace(tzinfo=None)})
    assert not oauth._fresh({"access_token": "", "expires_at": later})
