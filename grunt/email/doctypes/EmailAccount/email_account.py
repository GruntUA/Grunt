"""Controller for EmailAccount."""

from grunt.document.base import Document
from grunt.email.service import SMTP_PASSWORD_MASK


class EmailAccount(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    provider: str | None  # Mail service
    email_address: str | None  # Email address
    open_app_passwords: None  # Open the Google app passwords page
    smtp_user: str | None  # SMTP user
    smtp_password: str | None  # SMTP password (app password)
    test_connection: None  # Test connection (SMTP)
    test_send: None  # Send test email
    enable_outgoing: bool | None  # Enable outgoing mail
    smtp_server: str | None  # SMTP server
    smtp_port: int | None  # SMTP port
    use_tls: bool | None  # Use TLS
    enable_incoming: bool | None  # Enable incoming mail
    imap_server: str | None  # IMAP server
    imap_port: int | None  # IMAP port
    use_ssl: bool | None  # Use SSL

    # end: auto-generated types

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
