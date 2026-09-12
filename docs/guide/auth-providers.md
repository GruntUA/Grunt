# Authentication providers

Grunt authenticates with a small pluggable layer. A **provider** is one way of
proving identity — password, passkey (WebAuthn), an OIDC identity provider, a
magic link — behind a single two-step contract.

```
grunt/auth/
├── login.py                # issue_login(): the ONLY place tokens are minted
├── providers/
│   ├── base.py             # AuthProvider ABC + AuthFlowContext
│   ├── registry.py         # register() / get() / available()
│   ├── webauthn.py         # reference implementation (passkeys)
│   └── oauth.py            # Google / Microsoft OIDC
└── doctypes/WebAuthnCredential/   # one row per registered passkey
```

## HTTP surface

Mounted at `/api/v1/auth` ([`grunt/api/v1/auth_methods.py`](../../grunt/api/v1/auth_methods.py)):

| Method & path | Purpose |
|---|---|
| `GET  /api/v1/auth/methods` | Configured providers — drives the login screen |
| `POST /api/v1/auth/{name}/begin` | Start a sign-in ceremony |
| `POST /api/v1/auth/{name}/complete` | Finish it → **standard token payload** |
| `POST /api/v1/auth/{name}/enroll/begin` | Add the factor (signed-in user) |
| `POST /api/v1/auth/{name}/enroll/complete` | — |

`complete` always funnels through `grunt.auth.login.issue_login`, so its
response is byte-for-byte identical to `login_api` — including the
`mfa_required` gate. `login_api`, `mfa_login_api` and the OIDC callback all use
the same helper; there is no second token-minting code path.

## The contract

```python
class AuthProvider(ABC):
    name: str  # "webauthn"
    label: str  # "Passkey"
    kind: str  # "redirect" | "challenge"
    icon: str | None
    requires_identifier: bool = False  # begin() needs an email
    supports_enrollment: bool = False  # can enrol the factor for a user

    def is_configured(self) -> bool: ...  # hidden from /methods if False
    async def begin(self, ctx) -> dict: ...  # → JSON for the frontend
    async def complete(self, ctx) -> User: ...  # → the authenticated User

    # optional, only when supports_enrollment
    async def enroll_begin(self, ctx) -> dict: ...
    async def enroll_complete(self, ctx) -> dict: ...
```

`ctx` is an `AuthFlowContext` carrying `request`, `data` (the POST body),
`user` (the bearer user when present — enrolment flows), `ip_address` and
`user_agent`.

`kind` tells the frontend how to drive it:

* **`redirect`** — `begin` returns `{"redirect_url": ...}`; the browser
  navigates away. For OIDC the IdP calls back to
  `/api/v1/oauth/{provider}/callback`, which 302-redirects into the SPA at
  `{APP_URL}/login#access_token=…&refresh_token=…` (or `#mfa_required=1&mfa_token=…`,
  or `#error=…`). `Login.vue` reads the fragment, adopts the pair via
  `auth.setSession()` and strips it from the URL.
* **`challenge`** — `begin` returns an opaque payload for a browser API
  (`navigator.credentials.get`); its result is posted straight to `complete`.

## Adding a provider

```python
# myapp/auth/telegram.py
from grunt.api.messages import throw
from grunt.auth.providers import AuthProvider, register


class TelegramProvider(AuthProvider):
    name = "telegram"
    label = "Telegram"
    kind = "redirect"
    requires_identifier = False

    def is_configured(self) -> bool:
        from grunt.config import settings

        return bool(settings.telegram_bot_token)

    async def begin(self, ctx):
        return {"redirect_url": build_widget_url()}

    async def complete(self, ctx):
        data = verify_telegram_hash(ctx.data)  # or throw("bad hash", "UNAUTHORIZED")
        from grunt.auth.login import find_or_create_external_user

        return await find_or_create_external_user(data["email"], data["name"])


def register_providers() -> None:
    register(TelegramProvider())
```

Call `register_providers()` from your app's `hooks.py` (or import the module for
side effects). Built-in providers register lazily on first registry access.

> Raise API errors with `grunt.api.messages.throw(msg, "UNAUTHORIZED")` — the
> **code-based** `throw`. The `grunt.throw` bound on the app instance takes a
> *title*, not a code, and won't map to the right HTTP status.

## Stateless challenges

Multi-step ceremonies that need the server to remember something between two
requests use a signed, single-purpose JWT instead of server state:

```python
from grunt.auth.service import create_challenge_token, verify_challenge_token

token = create_challenge_token("telegram-login", ttl_minutes=5, nonce=nonce)
claims = verify_challenge_token(token, "telegram-login")  # None if wrong purpose / expired
```

`create_mfa_token` / `verify_mfa_token` are thin wrappers over these.

## WebAuthn / passkeys (reference)

Config:

```
WEBAUTHN_RP_ID=app.example.com          # DNS name only
WEBAUTHN_RP_NAME=Acme
WEBAUTHN_ORIGIN=https://app.example.com # full origin, https:// in prod
```

When `WEBAUTHN_RP_ID` / `WEBAUTHN_ORIGIN` are unset, both are derived from the
incoming request (`Origin` / `Host` + `X-Forwarded-Proto`), so a passkey works
on whatever host the app is actually served from. **Pin them in production** —
a stable `rp_id` lets one passkey cover every sub-domain, and the browser only
allows WebAuthn over HTTPS (or `localhost`); a non-HTTPS origin outside debug
logs `webauthn.insecure_origin`. The `rp_id`/`origin` used by `begin` are
sealed into the challenge token and re-checked by `complete`.

* **Storage** — one `WebAuthnCredential` row per passkey (`user`, `credential_id`,
  `public_key`, `sign_count`, `transports`, `backed_up`, `last_used_at`).
* **Sign in** — `POST /api/v1/auth/webauthn/begin` (optional `{email}` for a
  scoped `allowCredentials`, omit it for usernameless resident-key sign-in) →
  browser `navigator.credentials.get` → `POST .../complete`.
* **Sign in from a phone (QR)** — `begin` with `{mode: "cross-device"}`: forces
  a discoverable request (no `allowCredentials`, even with an email) and adds
  `hints: ["hybrid", "client-device"]` so the client shows "use a phone / scan
  QR" instead of the "insert a USB key" default. Frontend:
  `auth.loginWithPasskey(undefined, { mode: 'cross-device' })` /
  the **Увійти з телефона** button.
* **Enrol a phone passkey** — `enroll/begin` also honours `{mode: "cross-device"}`
  (`grunt.passkey.register(label, { mode: 'cross-device' })`, or the
  "Ключ на телефоні" checkbox on the User form).
* **Enrol** — `POST /api/v1/auth/webauthn/enroll/begin` (bearer token) →
  `navigator.credentials.create` → `.../enroll/complete`.
* **Frontend glue** — [`useWebAuthn.ts`](../../frontend/src/core/composables/useWebAuthn.ts)
  (base64url ↔ buffer + the two ceremonies), `authApi` in
  [`core/api/auth.ts`](../../frontend/src/core/api/auth.ts),
  `auth.loginWithPasskey()` in the store, and `grunt.passkey.*` for client
  scripts (used by the **Керувати ключами доступу** button on the User form).

## Sign in with email (magic link + one-time code)

Provider `email` ([`providers/email_link.py`](../../grunt/auth/providers/email_link.py)) —
passwordless login by an address the user types in. No config beyond a working
outgoing `EmailAccount` (`SystemSettings.default_email_account`, or the first
account with `enable_outgoing`); `begin` returns a `422` with a clear message
when none is set.

`kind = "challenge"`, `requires_identifier = true`. One `begin`, two ways to finish:

* **One-time code** — `POST /api/v1/auth/email/begin` `{email}` mails a 6-digit
  code and returns `{challenge_token, ttl_minutes}` (15 min). `POST .../complete`
  `{challenge_token, code}` needs **both**: the token proves this browser started
  the flow, the code proves inbox control. Wrong codes count against the account
  lock-out (`register_failed_attempt` — shared with password login); a locked
  account gets `429 RATE_LIMITED`.
* **Magic link** — the same mail carries
  `{APP_URL}/login#email_login_token=<jwt>`. `Login.vue`'s
  `consumeExternalRedirect()` lifts the fragment and posts `{token}` to
  `.../complete`. The link token is self-contained (inbox possession is the
  proof).

Both the code's keyed HMAC (`hmac(secret_key, "email:code")`) and the link token
are sealed into short-lived signed JWTs — no server state, like the WebAuthn
challenge. The HMAC key is the app secret, so a `challenge_token` leaked to an
attacker can't be brute-forced into the code offline, only against `complete`
(guarded by the lock-out).

An unknown address is provisioned as a passwordless user via
`find_or_create_external_user` — but only after `_guard_registration()` (so
`allow_user_registration = false` limits email login to existing users) and
`_apply_signup_approval()` (so `require_signup_approval` still holds the account
pending). `complete` funnels through `issue_login`, so MFA / approval gating is
identical to every other method.

* **Frontend glue** — `auth.beginEmailLogin(email)` / `auth.completeEmailLogin(...)`
  in the store, the **Надіслати код на пошту** button + code panel in `Login.vue`,
  the `email_login.html` mail template in `grunt/email/templates/`.
