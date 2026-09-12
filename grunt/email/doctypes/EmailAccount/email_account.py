"""Controller for EmailAccount."""

from __future__ import annotations

from grunt.document.base import Document
from grunt.email.service import SMTP_PASSWORD_MASK


class EmailAccount(Document):
    # begin: auto-generated types
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        email_address: str | None
        provider: str | None
        enable_outgoing: bool | None
        smtp_server: str | None
        smtp_port: int | None
        use_tls: bool | None
        smtp_user: str | None
        smtp_password: str | None
        enable_incoming: bool | None
        imap_server: str | None
        imap_port: int | None
        use_ssl: bool | None

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
