"""CAPTCHA verification for public web-form submissions.

A single provider (Cloudflare Turnstile) for now — the site-wide keys live in
``settings``, never on the ``WebForm`` document itself, since they're secrets
rather than per-form configuration. A form only opts in via its own
``captcha_enabled`` flag; verification is a graceful no-op whenever the site
hasn't configured a provider at all, even if a form asks for it.
"""

from __future__ import annotations

import httpx

from grunt import log
from grunt.config import settings

_VERIFY_URLS = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
}


async def verify_captcha(token: str | None, remote_ip: str) -> bool:
    """Verify a CAPTCHA response token against the configured provider.

    Returns True (allow) when no provider is configured site-wide, so a form
    with ``captcha_enabled`` set on a site that never set up ``captcha_*``
    settings degrades to "no CAPTCHA" rather than locking everyone out.
    """
    provider = settings.captcha_provider
    if not provider:
        return True

    verify_url = _VERIFY_URLS.get(provider)
    if not verify_url or not settings.captcha_secret_key:
        log.warning("webform.captcha_misconfigured", provider=provider)
        return True

    if not token:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                verify_url,
                data={
                    "secret": settings.captcha_secret_key,
                    "response": token,
                    "remoteip": remote_ip,
                },
            )
            resp.raise_for_status()
            return bool(resp.json().get("success"))
    except httpx.HTTPError:
        log.exception("webform.captcha_verify_failed", provider=provider)
        return False
