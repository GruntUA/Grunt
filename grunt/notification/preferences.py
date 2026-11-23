"""What a person turned off - ``NotificationPreference`` rows.

A row says "don't send me *notification* through *channel*"; an empty
``notification`` means every notification (and, for email, the digest), an
empty ``channel`` - every channel. Rows are made in the profile
(Preferences → Notifications), from the bell ("Don't send these") and by the
unsubscribe link in a letter (:mod:`grunt.email.unsubscribe`, channel
``email``).

The dispatcher (:func:`grunt.notification.delivery.deliver`) asks
:func:`muted` once per message and skips what is off - unless the rule is
mandatory (``Notification.is_mandatory``). A notification sent from code
without a rule is covered only by the "all notifications" rows.
"""

from collections.abc import Iterable
from typing import Any

from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.utils.attr_dict import AttrDict
lazy from grunt.document.api import documents
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.permissions.rbac import permission_checker

DOCTYPE = "NotificationPreference"
WEBHOOK = "webhook"  # goes to a URL, not to a person - nothing to turn off

_db = GruntDB()  # stateless: reads through the context's session

#: ``(email, channel)`` pairs that are off; channel None - every channel.
Muted = set[tuple[str, str | None]]


def normal(email: str | None) -> str:
    return (email or "").strip().lower()


async def muted(recipients: Iterable[str], notification: str | None, session: Any = None) -> Muted:
    """What *recipients* turned off for *notification* (None - a notification
    without a rule: only the "all notifications" rows count). Reads through
    *session*, or the context's one when not given."""
    emails = sorted({normal(r) for r in recipients if r})
    if not emails:
        return set()
    either: dict[str, Any] = {"notification__isnull": True}
    if notification:
        either["notification"] = notification
    async with system_context(session if session is not None else require_session()):
        rows = await _db.get_all(
            DOCTYPE,
            filters={"email__in": emails},
            or_filters=either,
            fields=["email", "channel"],
            limit=None,
        )
    return {(r.email, r.channel or None) for r in rows}


def is_off(off: Muted, email: str, channel: str) -> bool:
    """Whether *email* turned *channel* off, by the pairs :func:`muted` gave."""
    address = normal(email)
    return (address, channel) in off or (address, None) in off


async def is_muted(email: str, notification: str | None, channel: str) -> bool:
    """Whether *email* turned off *notification* (None - all) in *channel*."""
    return is_off(await muted([email], notification), email, channel)


async def _rows(email: str, notification: str | None) -> list[AttrDict]:
    filters: dict[str, Any] = {"email": normal(email)}
    if notification:
        filters["notification"] = notification
    else:
        filters["notification__isnull"] = True
    return await _db.get_all(DOCTYPE, filters=filters, fields=["name", "channel"], limit=None)


async def set_enabled(
    email: str,
    notification: str | None,
    channel: str,
    enabled: bool,
    channels: Iterable[str] = (),
) -> None:
    """Turn *notification* (None - all notifications) on or off in *channel*
    for *email*.

    Turning on a channel a row for every channel covers splits that row: the
    other *channels* (the registered ones) stay off, each in its own row."""
    address = normal(email)
    if not address or not channel:
        return
    rows = await _rows(address, notification)
    exact = [r for r in rows if r.channel == channel]
    every = [r for r in rows if not r.channel]
    if not enabled:
        if not exact and not every:
            await documents.new_doc(
                DOCTYPE,
                {"email": address, "notification": notification, "channel": channel},
                ignore_permissions=True,
            )
            log.info("notification.muted", notification=notification or "*", channel=channel)
        return
    for row in exact:
        await _db.delete(DOCTYPE, row.name)
    if every:
        for row in every:
            await _db.delete(DOCTYPE, row.name)
        kept = {r.channel for r in rows}
        for other in channels:
            if other not in (channel, WEBHOOK) and other not in kept:
                await documents.new_doc(
                    DOCTYPE,
                    {"email": address, "notification": notification, "channel": other},
                    ignore_permissions=True,
                )
    log.info("notification.unmuted", notification=notification or "*", channel=channel)


async def mute_everywhere(email: str, notification: str) -> None:
    """Turn *notification* off in every channel for *email* (the bell's
    "Don't send these")."""
    address = normal(email)
    if not address or not notification:
        return
    for row in await _rows(address, notification):
        await _db.delete(DOCTYPE, row.name)
    await documents.new_doc(
        DOCTYPE,
        {"email": address, "notification": notification, "channel": None},
        ignore_permissions=True,
    )
    log.info("notification.muted", notification=notification, channel="*")


async def _readable(doctype: str) -> bool:
    try:
        meta = await doctype_registry.get_meta(doctype)
    except Exception:  # noqa: BLE001 - a DocType gone from the site: nothing to show
        return False
    return meta is not None and await permission_checker.check(meta.doc, "read", None)


async def overview(email: str, channels: list[dict[str, Any]]) -> dict[str, Any]:
    """The profile's table: *channels* (``{"value", "label"}``; webhook left
    out), the rules *email* could get with the channels each sends through,
    and what is off.

    A rule shows when it is enabled, sends to a person (not only a webhook) and
    is about a DocType the current user can read (or about none - an event
    from code)."""
    rules = await _db.get_all(
        "Notification",
        filters={"is_enabled": True},
        fields=["name", "ref_doctype", "is_mandatory"],
        order_by="name",
        order="asc",
        limit=None,
    )
    channel_rows = await _db.get_all(
        "NotificationChannel",
        filters={"parent_doctype": "Notification"},
        fields=["parent_name", "channel"],
        limit=None,
    )
    rows = await _db.get_all(
        DOCTYPE,
        filters={"email": normal(email)},
        fields=["notification", "channel"],
        limit=None,
    )
    by_rule: dict[str, list[str]] = {}
    for row in channel_rows:
        if row.channel and row.channel != WEBHOOK:
            names = by_rule.setdefault(row.parent_name, [])
            if row.channel not in names:
                names.append(row.channel)
    readable: dict[str, bool] = {}
    shown: list[dict[str, Any]] = []
    for rule in rules:
        sends = by_rule.get(rule.name)
        if not sends:
            continue
        doctype = rule.ref_doctype
        if doctype:
            if doctype not in readable:
                readable[doctype] = await _readable(doctype)
            if not readable[doctype]:
                continue
        shown.append(
            {
                "name": rule.name,
                "label": _(rule.name),
                "ref_doctype": doctype or None,
                "channels": sends,
                "mandatory": bool(rule.is_mandatory),
            }
        )
    return {
        "channels": [c for c in channels if c["value"] != WEBHOOK],
        "rules": shown,
        "off": [
            {"notification": r.notification or None, "channel": r.channel or None} for r in rows
        ],
    }
