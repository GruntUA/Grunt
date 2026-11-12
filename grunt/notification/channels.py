"""Notification channels - how one notification reaches one recipient.

A channel is a class with a ``name`` (stored in rules and in the delivery
log), a ``label`` and :meth:`Channel.send`. The core ships ``in_app`` (the
bell + a realtime ping), ``web_push`` (browser push) and ``email`` (the email
queue); an app adds its own (SMS, a messenger, …) in its ``hooks.py``::

    notification_channels = ["my_app.sms.SmsChannel"]

and it becomes available to every notification rule (apps load in the web
server and the worker alike). The core's channels register on import.

Channels don't decide *whether* to notify - rules and the dispatcher
(:mod:`grunt.notification.delivery`) do; a channel only carries one message to
one recipient and reports the :class:`Outcome`, which the dispatcher writes to
the ``NotificationDelivery`` log.
"""

import importlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

import grunt.outbox as outbox
from grunt.api.v1.ws import manager
from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.i18n import N_, _
from grunt.local import system_context
from grunt.log import log
from grunt.metadata.dynamic_options import register_option_provider
from grunt.notification.delivery_log import Status
lazy from grunt.email.service import email_service
lazy from grunt.metadata.registry import doctype_registry
lazy from grunt.webpush.service import deliver_push

_db = GruntDB()  # stateless: reads through the context's session


@dataclass(slots=True)
class Message:
    """What to tell a recipient - the same for every channel; a channel takes
    the parts it can carry (an SMS - the subject, an email - the HTML too)."""

    subject: str
    body: str = ""
    html: str | None = None
    url: str | None = None
    ref_doctype: str | None = None
    doc_id: str | None = None
    notification: str | None = None  # the rule that sent it
    event_key: str | None = None  # the code event, for notifications raised from code


@dataclass(slots=True)
class Outcome:
    """What a channel did: ``Sent`` (done), ``Queued`` (handed to a queue - the
    queue settles it later), ``Skipped`` (nothing to do - e.g. no address) or
    ``Error``. ``links`` - log fields pointing at what the channel created."""

    status: Status
    reason: str | None = None
    links: dict[str, str] = field(default_factory=dict)


class Channel:
    """Base class of a notification channel."""

    name: ClassVar[str]
    label: ClassVar[str]

    async def send(
        self, session: AsyncSession, recipient: str, message: Message, *, delivery: str
    ) -> Outcome:
        """Deliver *message* to *recipient* (a user's email); *delivery* - the
        name of the ``NotificationDelivery`` row the outcome goes to (a queued
        channel passes it on to settle it later)."""
        raise NotImplementedError


async def desk_url(doctype: str | None, doc_id: str | None) -> str | None:
    """The document's form in the desk, or None when it can't be told.

    Loads the definition when needed - the worker knows only DocType names
    until something asks for one (a Studio DocType has no class to index)."""
    if not doctype or not doc_id:
        return None
    try:
        meta = await doctype_registry.get_meta(doctype)
    except Exception:  # noqa: BLE001 - a link is a nicety; no definition, no link
        meta = None
    if meta is None:
        return None
    dt = meta.doc
    app = getattr(dt, "app", None) or getattr(dt, "module", None) or "grunt"
    return f"/app/{app}/{doctype}/{doc_id}"


class InAppChannel(Channel):
    """The bell: a ``NotificationLog`` row and a realtime ping after the commit."""

    name = "in_app"
    label = N_("In the system")

    async def send(
        self, session: AsyncSession, recipient: str, message: Message, *, delivery: str
    ) -> Outcome:
        log_id = f"notif-{recipient}-{delivery[3:11]}"
        now = datetime.now(UTC)
        async with system_context(session):
            await _db.insert_one(
                "NotificationLog",
                {
                    "name": log_id,
                    "owner": recipient,
                    "created_at": now,
                    "modified_at": now,
                    "modified_by": recipient,
                    "user": recipient,
                    "ref_doctype": message.ref_doctype,
                    "doc_id": message.doc_id,
                    "subject": message.subject,
                    "message": message.body,
                    "is_read": False,
                    "notification": message.notification,
                },
            )
        payload = {
            "event": "notification",
            "data": {
                "subject": message.subject,
                "message": message.body,
                "ref_doctype": message.ref_doctype,
                "doc_id": message.doc_id,
            },
        }

        async def ping() -> None:
            # After the commit: the bell's reload then finds the new row.
            try:
                await manager.send_to_user(recipient, payload)
            except Exception:
                log.debug("notification.ws_send_error", recipient=recipient)

        on_commit(ping, session=session)
        return Outcome("Sent", links={"notification_log": log_id})


class WebPushChannel(Channel):
    """Browser push, sent by a worker after the commit (the push service may be
    slow); the worker settles the delivery - no subscription, push disabled…"""

    name = "web_push"
    label = N_("Browser push")

    async def send(
        self, session: AsyncSession, recipient: str, message: Message, *, delivery: str
    ) -> Outcome:
        url = message.url or await desk_url(message.ref_doctype, message.doc_id) or "/"
        await outbox.put(
            deliver_push,
            {
                "user": recipient,
                "subject": message.subject,
                "body": message.body,
                "url": url,
                "delivery": delivery,
            },
            session=session,
        )
        return Outcome("Queued")


class EmailChannel(Channel):
    """A letter through the email queue; the queue worker settles the delivery."""

    name = "email"
    label = N_("Email")

    async def send(
        self, session: AsyncSession, recipient: str, message: Message, *, delivery: str
    ) -> Outcome:
        queue_id = await email_service.queue_email(
            session=session,
            to=recipient,
            subject=message.subject,
            body=message.body,
            html_body=message.html,
        )
        if not queue_id:
            return Outcome("Error", reason=_("The email could not be queued"))
        return Outcome("Queued", links={"email_queue": queue_id})


# name -> channel instance
_channels: dict[str, Channel] = {}


def register_channel(channel: type[Channel] | Channel | str) -> Channel:
    """Add a channel (a class, an instance or a dotted path to the class);
    a later one with the same name replaces the earlier."""
    target: object = channel
    if isinstance(channel, str):
        module_path, attr = channel.rsplit(".", 1)
        target = getattr(importlib.import_module(module_path), attr)
    instance = target() if isinstance(target, type) else target
    if not isinstance(instance, Channel) or not getattr(instance, "name", None):
        raise ValueError(f"notification channel {channel!r} is not a named Channel")
    _channels[instance.name] = instance
    return instance


def get_channel(name: str) -> Channel | None:
    return _channels.get(name)


def list_channels() -> list[Channel]:
    return list(_channels.values())


def channel_options() -> list[dict[str, Any]]:
    """``[{"value", "label"}]`` - for a rule's channel picker."""
    return [{"value": c.name, "label": _(c.label)} for c in _channels.values()]


#: ``options_source`` of ``NotificationChannel.channel`` - the registered channels.
OPTIONS_SOURCE = "grunt.notification.channel"
register_option_provider(OPTIONS_SOURCE, lambda: [(c.name, _(c.label)) for c in list_channels()])


CORE_CHANNELS = (InAppChannel, WebPushChannel, EmailChannel)
for _core in CORE_CHANNELS:
    register_channel(_core)
