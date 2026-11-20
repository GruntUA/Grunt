"""Controller for EmailAccount."""

from grunt.document.base import Document
from grunt.email.service import SMTP_PASSWORD_MASK
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry


class EmailAccount(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    provider: str | None  # Mail service
    email_address: str  # Email address
    smtp_user: str | None  # SMTP user
    smtp_password: str | None  # SMTP password (app password)
    enable_outgoing: bool | None  # Enable outgoing mail
    smtp_server: str | None  # SMTP server
    smtp_port: int | None  # SMTP port
    use_tls: bool | None  # Use TLS
    enable_incoming: bool | None  # Enable incoming mail
    imap_server: str | None  # IMAP server
    imap_port: int | None  # IMAP port
    use_ssl: bool | None  # Use SSL
    imap_folders: str | None  # IMAP folders
    imap_state: dict | None  # IMAP position
    append_to: str | None  # Create documents
    auto_reply: bool | None  # Auto-reply
    auto_reply_message: str | None  # Auto-reply text
    notify_if_unreplied: bool | None  # Notify if not answered
    unreplied_minutes: int | None  # Minutes without a reply
    unreplied_group: str | None  # Notify group
    signature: str | None  # Signature
    reply_to: str | None  # Reply-To
    always_bcc: str | None  # Always BCC

    # end: auto-generated types

    async def validate(self) -> None:
        if self.append_to:
            meta = await doctype_registry.get_meta(self.append_to)
            if meta is None or not meta.email_append_to:
                throw(
                    _(
                        "“%(doctype)s” does not take incoming mail: turn on “Create from"
                        " incoming mail” in its settings first"
                    )
                    % {"doctype": self.append_to}
                )
        if self.notify_if_unreplied and (self.unreplied_minutes or 0) < 1:
            self.unreplied_minutes = 30

    async def before_save(self) -> None:
        await self._keep_password_when_masked()

    async def _keep_password_when_masked(self) -> None:
        """Don't let the read-time placeholder overwrite the real password.

        Reads return ``SMTP_PASSWORD_MASK`` instead of the stored value
        (see ``grunt.email.hooks.mask_smtp_password``), so a plain "load form,
        edit something else, save" round-trip would otherwise wipe the password.
        Treat an empty or placeholder value as "unchanged" and restore whatever
        is already in the database.
        """
        pw = (self.smtp_password or "").strip()
        if pw and pw != SMTP_PASSWORD_MASK:
            self.smtp_password = pw
            return

        stored = None
        if self.name:
            stored = await self.grunt.db.get_value("EmailAccount", self.name, "smtp_password")
        self.smtp_password = stored
