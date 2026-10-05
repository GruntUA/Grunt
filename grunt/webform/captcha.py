"""CAPTCHA verification for public forms (web forms, app pages).

A single provider (Cloudflare Turnstile) for now. The site-wide keys live in
``SystemSettings`` (tab Security → CAPTCHA), with the ``captcha_*`` settings
of ``grunt.config`` as a fallback for sites configured through the
environment — never on a form itself, since they're secrets rather than
per-form configuration. A form only opts in via its own flag (e.g.
``WebForm.captcha_enabled``); verification is a graceful no-op whenever the
site hasn't configured a provider at all, even if a form asks for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from grunt import log
from grunt.config import settings

_VERIFY_URLS = {
    "turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
}
# Turnstile's widget script and the field it posts its token in.
TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js"
TOKEN_FIELD = "cf-turnstile-response"


@dataclass(frozen=True)
class CaptchaConfig:
    provider: str | None
    site_key: str | None
    secret_key: str | None


async def captcha_config() -> CaptchaConfig:
    """Site CAPTCHA settings: SystemSettings first, then ``grunt.config``."""
    from grunt.site.settings import get_setting

    provider = await get_setting("captcha_provider")
    if provider:
        return CaptchaConfig(
            provider,
            await get_setting("captcha_site_key"),
            await get_setting("captcha_secret_key"),
        )
    return CaptchaConfig(
        settings.captcha_provider, settings.captcha_site_key, settings.captcha_secret_key
    )


async def captcha_site_key() -> str | None:
    """Public key for the widget, or None when CAPTCHA is off site-wide."""
    config = await captcha_config()
    return config.site_key if config.provider and config.site_key else None


async def verify_captcha(token: str | None, remote_ip: str) -> bool:
    """Verify a CAPTCHA response token against the configured provider.

    Returns True (allow) when no provider is configured site-wide, so a form
    asking for CAPTCHA on a site that never set up the keys degrades to
    "no CAPTCHA" rather than locking everyone out.
    """
    config = await captcha_config()
    if not config.provider:
        return True

    verify_url = _VERIFY_URLS.get(config.provider)
    if not verify_url or not config.secret_key or not config.site_key:
        log.warning("webform.captcha_misconfigured", provider=config.provider)
        return True

    if not token:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                verify_url,
                data={
                    "secret": config.secret_key,
                    "response": token,
                    "remoteip": remote_ip,
                },
            )
            resp.raise_for_status()
            return bool(resp.json().get("success"))
    except httpx.HTTPError:
        log.exception("webform.captcha_verify_failed", provider=config.provider)
        return False
