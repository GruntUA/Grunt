"""Unsubscribing from notification emails.

A letter a :class:`~grunt.notification.doctypes.Notification` rule sends by
email (and the digest) carries ``List-Unsubscribe`` + ``List-Unsubscribe-Post``
(one click, RFC 8058) and a link at the bottom. The link opens a page that asks
"this kind of letter or all notification emails?"; a mail client's one-click
POST unsubscribes from the rule at once. Either way a ``NotificationPreference``
row (channel ``email``) remembers it, and the dispatcher skips the address from
then on. A mandatory rule's letter has no link.

Only notifications: sign-in codes, password resets and letters written from a
document are never unsubscribable. The link is signed with the site's secret
for the address - it can't be made for someone else's.
"""

import hashlib
import hmac
from html import escape
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse

from grunt.api.context import whitelist
from grunt.config import settings
from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.local import require_session, system_context
lazy from grunt.notification import preferences
lazy from grunt.site.manager import current_site

_db = GruntDB()  # stateless: reads through the context's session

ENDPOINT = "/api/v1/method/grunt.email.unsubscribe.unsubscribe"


def _normal(email: str | None) -> str:
    return (email or "").strip().lower()


def make_token(email: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), f"unsubscribe:{_normal(email)}".encode(), hashlib.sha256
    ).hexdigest()[:32]


def valid_token(email: str, token: str) -> bool:
    return bool(email) and hmac.compare_digest(make_token(email), token or "")


def _site_base() -> str:
    """The site's public origin - by its domain when it is named by one (a
    letter is built in the worker, with no request to read it from)."""
    site = current_site.get() or ""
    return f"https://{site}" if "." in site else settings.app_url.rstrip("/")


def unsubscribe_url(email: str, notification: str | None = None) -> str:
    """The signed link that unsubscribes *email* from *notification* (None -
    from all notification emails)."""
    query = {"email": _normal(email), "token": make_token(email)}
    if notification:
        query["notification"] = notification
    return f"{_site_base()}{ENDPOINT}?{urlencode(query)}"


async def is_unsubscribed(email: str, notification: str | None = None) -> bool:
    """Whether *email* turned off *notification* letters (or all of them).
    ``notification=None`` asks about "all" only (the digest)."""
    return await preferences.is_muted(email, notification, "email")


async def add(email: str, notification: str | None = None) -> None:
    """Remember that *email* does not want *notification* letters (None - any)."""
    await preferences.set_enabled(email, notification, "email", False)


def footer(url: str) -> tuple[str, str]:
    """The (HTML, text) line appended to an unsubscribable letter."""
    label = _("Unsubscribe from these emails")
    html = (
        '<p style="margin-top:24px;font-size:12px;color:#888">'
        f'<a href="{escape(url, quote=True)}" style="color:#888">{escape(label)}</a></p>'
    )
    return html, f"{label}: {url}"


# The page


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;"
        "padding:0 1rem;color:#222;line-height:1.5}button{font:inherit;padding:.5rem 1rem;"
        "margin:.25rem .5rem .25rem 0;border:1px solid #888;border-radius:.375rem;"
        "background:#fff;cursor:pointer}button.primary{background:#222;color:#fff}</style>"
        f"</head><body><h1 style='font-size:1.25rem'>{escape(title)}</h1>{body}</body></html>"
    )


def _form(email: str, token: str, notification: str | None, label: str, primary: bool) -> str:
    fields = {
        "email": email,
        "token": token,
        **({"notification": notification} if notification else {}),
    }
    hidden = "".join(
        f"<input type='hidden' name='{k}' value='{escape(v, quote=True)}'>"
        for k, v in fields.items()
    )
    css = " class='primary'" if primary else ""
    return (
        f"<form method='post' action='{ENDPOINT}' style='display:inline'>"
        f"{hidden}<button{css}>{escape(label)}</button></form>"
    )


@whitelist(allow_guest=True)
async def unsubscribe(
    email: str = "",
    token: str = "",
    notification: str = "",
    request: Request | None = None,
) -> HTMLResponse:
    """The link in a notification letter: GET asks, POST unsubscribes (the
    page's buttons and a mail client's one-click ``List-Unsubscribe-Post``)."""
    address = _normal(email)
    if not valid_token(address, token):
        return _page(
            _("The link is invalid"), f"<p>{escape(_('Open the link from the letter again.'))}</p>"
        )
    rule = notification or None
    async with system_context(require_session()):
        if rule and not await _db.exists("Notification", rule):
            rule = None
        if request is not None and request.method == "POST":
            await add(address, rule)
            await require_session().commit()
            what = _("“%(name)s” letters") % {"name": _(rule)} if rule else _("notification emails")
            return _page(
                _("You are unsubscribed"),
                "<p>"
                + escape(
                    _("%(email)s will no longer get %(what)s.") % {"email": address, "what": what}
                )
                + "</p>",
            )
    buttons = ""
    if rule:
        buttons += _form(
            address, token, rule, _("Unsubscribe from “%(name)s”") % {"name": _(rule)}, True
        )
    buttons += _form(address, token, None, _("Unsubscribe from all notification emails"), not rule)
    return _page(
        _("Unsubscribe"),
        f"<p>{escape(_('Which letters should %(email)s no longer get?') % {'email': address})}</p>"
        f"<p>{buttons}</p>",
    )
