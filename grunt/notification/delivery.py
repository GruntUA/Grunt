"""The dispatcher - every notification goes out through :func:`deliver`.

For each recipient × channel it asks the channel to send and writes the
outcome to the ``NotificationDelivery`` log: who was told what, through which
channel, why not (no such channel, channel failed) - and, for queued channels,
whether it finally arrived (the email queue / the push sender settle the row).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.i18n import _
from grunt.log import log
from grunt.notification import delivery_log
from grunt.notification.channels import Message, Outcome, get_channel


@dataclass(slots=True)
class Report:
    """What :func:`deliver` did - counts per status and the bell rows it made."""

    counts: dict[str, int] = field(default_factory=dict)
    notification_logs: list[str] = field(default_factory=list)
    reached: set[str] = field(default_factory=set)  # recipients a channel sent or queued to

    @property
    def delivered(self) -> int:
        """Deliveries that went out or were queued - not skipped, not failed."""
        return self.counts.get("Sent", 0) + self.counts.get("Queued", 0)


async def deliver(
    session: AsyncSession,
    recipients: Iterable[str],
    message: Message,
    channels: Iterable[str],
) -> Report:
    """Send *message* to every recipient (user email) through every channel."""
    report = Report()
    names = list(dict.fromkeys(c for c in channels if c))
    for recipient in dict.fromkeys(r for r in recipients if r):
        for name in names:
            delivery = delivery_log.new_id()
            channel = get_channel(name)
            if channel is None:
                outcome = Outcome(
                    "Skipped", reason=_("Unknown channel “%(channel)s”") % {"channel": name}
                )
            else:
                try:
                    outcome = await channel.send(session, recipient, message, delivery=delivery)
                except Exception as exc:  # noqa: BLE001 - one channel must not stop the rest
                    log.exception("notification.channel_failed", channel=name, recipient=recipient)
                    outcome = Outcome("Error", reason=str(exc))
            report.counts[outcome.status] = report.counts.get(outcome.status, 0) + 1
            if outcome.status in ("Sent", "Queued"):
                report.reached.add(recipient)
            if log_id := outcome.links.get("notification_log"):
                report.notification_logs.append(log_id)
            try:
                await delivery_log.record(
                    {
                        "name": delivery,
                        "notification": message.notification,
                        "event_key": message.event_key,
                        "ref_doctype": message.ref_doctype,
                        "doc_id": message.doc_id,
                        "recipient": recipient,
                        "channel": name,
                        "status": outcome.status,
                        "reason": outcome.reason,
                        "subject": message.subject,
                        **outcome.links,
                    },
                    session=session,
                )
            except Exception:
                log.exception("notification.delivery_record_failed", channel=name)
    return report
