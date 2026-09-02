"""'Sign in with email' provider — passwordless login by a one-time code or a
magic link mailed to the address the user types in.

One ``begin`` call, two ways to finish:

* **code** — ``begin`` hands the browser a ``challenge_token`` and mails a
  6-digit code. ``complete`` needs *both*: the token proves this browser started
  the flow, the code proves the person controls the inbox.
* **magic link** — the same mail carries
  ``{base_url}/login#email_login_token=…``. ``Login.vue`` lifts the fragment and
  posts the self-contained ``token`` to ``complete``.

Both JWTs point at one ``EmailLoginToken`` row (``tid`` claim). Signing in by
*either* path marks that row ``consumed_at`` — so the other path (and any replay)
immediately stops working. A fresh ``begin`` for the same address drops the
previous row. The row also holds the code's keyed HMAC, so nothing brute-forceable
ever leaves the server.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from grunt.api.messages import throw
from grunt.auth.providers.base import AuthFlowContext, AuthProvider
from grunt.auth.providers.registry import register
from grunt.auth.service import create_challenge_token, verify_challenge_token
from grunt.config import settings

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

logger = structlog.get_logger()

_CODE_PURPOSE = "email-login-code"
_LINK_PURPOSE = "email-login-link"
_TTL_MINUTES = 15
_TOKEN_DT = "EmailLoginToken"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm_email(raw: str | None) -> str:
    email = (raw or "").strip().lower()
    if not _EMAIL_RE.match(email):
        throw("Введіть коректну адресу електронної пошти", "VALIDATION_ERROR")
    return email


def _hash_code(email: str, code: str) -> str:
    """Keyed digest of the code — stored server-side, never sent to the client."""
    msg = f"{email}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()


class EmailLoginProvider(AuthProvider):
    name = "email"
    label = "Електронна пошта"
    kind: ClassVar = "challenge"
    icon = "mail"
    requires_identifier = True

    # ── sign in ────────────────────────────────────────────────────────────

    async def begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        email = _norm_email(ctx.get("email"))
        code = f"{secrets.randbelow(1_000_000):06d}"

        tid = await self._new_token(email, _hash_code(email, code), ctx.ip_address)
        challenge_token = create_challenge_token(
            _CODE_PURPOSE, ttl_minutes=_TTL_MINUTES, email=email, tid=tid
        )
        link_token = create_challenge_token(
            _LINK_PURPOSE, ttl_minutes=_TTL_MINUTES, email=email, tid=tid
        )
        login_url = f"{ctx.base_url()}/login#email_login_token={link_token}"
        await self._send_mail(email, code, login_url)
        return {"challenge_token": challenge_token, "ttl_minutes": _TTL_MINUTES}

    async def complete(self, ctx: AuthFlowContext) -> User:
        from grunt.auth.doctypes.User.user import (
            clear_failed_attempts,
            get_user_by_email,
            is_account_locked,
            register_failed_attempt,
        )

        # ── magic link — the token came from the inbox, that's the proof ──
        magic = ctx.get("token")
        if magic:
            claims = verify_challenge_token(magic, _LINK_PURPOSE)
            if not claims:
                throw("Посилання недійсне або застаріле", "UNAUTHORIZED")
            assert claims  # throw() above is NoReturn
            await self._consume(
                str(claims.get("tid") or ""),
                "Посилання недійсне або вже використане. Запросіть новий код.",
            )
            return await self._resolve_user(str(claims["email"]))

        # ── one-time code — needs the browser's token *and* the mailed code ──
        challenge_token = ctx.get("challenge_token")
        code = (ctx.get("code") or "").strip()
        if not challenge_token or not code:
            throw("Введіть код підтвердження", "VALIDATION_ERROR")

        claims = verify_challenge_token(challenge_token, _CODE_PURPOSE)
        if not claims:
            throw("Час дії коду вичерпано. Запросіть новий.", "UNAUTHORIZED")
        assert claims
        email = str(claims["email"])
        tid = str(claims.get("tid") or "")

        row = await self._load_active(tid)
        if row is None:
            throw("Код недійсний або вже використаний. Запросіть новий.", "UNAUTHORIZED")
        assert row

        user = await get_user_by_email(email)
        if user is not None:
            if not user.is_active:
                throw("Обліковий запис деактивовано", "UNAUTHORIZED")
            if await is_account_locked(user):
                throw("Забагато невдалих спроб. Спробуйте пізніше.", "RATE_LIMITED")

        if not hmac.compare_digest(
            str(row.get("code_hash") or ""), _hash_code(email, code)
        ):
            if user is not None:
                await register_failed_attempt(user)
            # A wrong guess does NOT burn the token — the user can retry.
            throw("Невірний код підтвердження", "UNAUTHORIZED")

        await self._mark_consumed(tid)
        if user is not None:
            await clear_failed_attempts(user)
            return user
        # New address — provision only now that the code has checked out.
        return await self._resolve_user(email)

    # ── EmailLoginToken row lifecycle ───────────────────────────────────────

    async def _new_token(self, email: str, code_hash: str, ip: str | None) -> str:
        from grunt.app import grunt
        from grunt.context import require_session

        now = datetime.now(UTC)
        async with grunt.system_context(require_session()):
            # One live token per address, and opportunistically sweep expired rows.
            await grunt.db.delete(_TOKEN_DT, {"email": email})
            await grunt.db.delete(_TOKEN_DT, {"expires_at__lt": now})
            doc = await grunt.new_doc(
                _TOKEN_DT,
                {
                    "email": email,
                    "code_hash": code_hash,
                    "expires_at": now + timedelta(minutes=_TTL_MINUTES),
                    "ip_address": ip or None,
                },
            )
        return doc["name"]

    async def _load_active(self, tid: str) -> dict | None:
        """The row for *tid* if it exists, is unconsumed and unexpired."""
        if not tid:
            return None
        from grunt.app import grunt
        from grunt.context import require_session

        async with grunt.system_context(require_session()):
            rows = await grunt.get_list(
                _TOKEN_DT,
                filters={"name": tid},
                fields=["name", "code_hash", "expires_at", "consumed_at"],
                limit=1,
            )
        if not rows:
            return None
        row = rows[0]
        if row.get("consumed_at"):
            return None
        exp = row.get("expires_at")
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp and exp.replace(tzinfo=UTC) < datetime.now(UTC):
            return None
        return row

    async def _mark_consumed(self, tid: str) -> None:
        from grunt.app import grunt
        from grunt.context import require_session

        async with grunt.system_context(require_session()):
            await grunt.db.set_value(_TOKEN_DT, tid, {"consumed_at": datetime.now(UTC)})

    async def _consume(self, tid: str, error: str) -> None:
        """Load-and-burn in one step (magic-link path, no extra factor)."""
        if await self._load_active(tid) is None:
            throw(error, "UNAUTHORIZED")
        await self._mark_consumed(tid)

    # ── helpers ────────────────────────────────────────────────────────────

    async def _resolve_user(self, email: str) -> User:
        """Existing active user, or a freshly provisioned passwordless one."""
        from grunt.auth.doctypes.User.user import (
            _apply_signup_approval,
            _guard_registration,
            get_user_by_email,
        )
        from grunt.auth.login import find_or_create_external_user

        user = await get_user_by_email(email)
        if user is not None:
            if not user.is_active:
                throw("Обліковий запис деактивовано", "UNAUTHORIZED")
            return user

        await _guard_registration()
        user = await find_or_create_external_user(email, email.split("@")[0])
        await _apply_signup_approval(user)
        return user

    async def _send_mail(self, email: str, code: str, login_url: str) -> None:
        from grunt.app import grunt
        from grunt.context import require_session
        from grunt.email.service import email_service

        plain = (
            f"Ваш код для входу: {code}\n\n"
            f"Код дійсний {_TTL_MINUTES} хвилин.\n\n"
            f"Або увійдіть одразу за посиланням:\n{login_url}\n\n"
            "Якщо ви не намагалися увійти — просто проігноруйте цей лист."
        )
        try:
            html_body: str | None = await grunt.render_template(
                "email_login.html",
                {"code": code, "login_url": login_url, "ttl_minutes": _TTL_MINUTES},
            )
        except Exception:
            logger.warning("auth.email_login.template_failed")
            html_body = None

        session = require_session()
        if await email_service.resolve_outgoing_account_id(session) is None:
            throw(
                "Вхід через пошту недоступний — не налаштовано поштовий сервер",
                "VALIDATION_ERROR",
            )
        queued = await email_service.queue_email(
            session=session,
            to=email,
            subject="Код для входу",
            body=plain,
            html_body=html_body,
        )
        await session.flush()
        if not queued:
            logger.warning("auth.email_login.queue_failed", email=email)
        else:
            logger.info("auth.email_login.sent", email=email)


def register_provider() -> None:
    register(EmailLoginProvider())
