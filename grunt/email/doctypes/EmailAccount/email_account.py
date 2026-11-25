"""Controller for EmailAccount."""

from typing import Any

from grunt.document.base import Document
from grunt.email.service import SMTP_PASSWORD_MASK
from grunt.errors import throw
from grunt.i18n import _
from grunt.integrations.oauth import disconnect_reference
from grunt.metadata.registry import doctype_registry

#: Servers of the mail services the form knows - filled in, not typed.
PRESETS: dict[str, dict[str, Any]] = {
    "Gmail": {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": True,
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "use_ssl": True,
    },
    "Microsoft 365": {
        "smtp_server": "smtp.office365.com",
        "smtp_port": 587,
        "use_tls": True,
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "use_ssl": True,
    },
}

#: What a mailbox asks a ConnectedApp for: IMAP + SMTP over XOAUTH2.
OAUTH_SCOPES: dict[str, list[str]] = {
    "Google": ["https://mail.google.com/"],
    "Microsoft": [
        "https://outlook.office.com/IMAP.AccessAsUser.All",
        "https://outlook.office.com/SMTP.Send",
    ],
}


class EmailAccount(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    provider: str | None = None  # Mail service
    email_address: str  # Email address
    auth_method: str | None = None  # Sign-in
    connected_app: str | None = None  # Connected app
    oauth_account: str | None = None  # Connected account
    smtp_user: str | None = None  # SMTP user
    smtp_password: str | None = None  # SMTP password (app password)
    enable_outgoing: bool | None = None  # Enable outgoing mail
    smtp_server: str | None = None  # SMTP server
    smtp_port: int | None = None  # SMTP port
    use_tls: bool | None = None  # Use TLS
    enable_incoming: bool | None = None  # Enable incoming mail
    imap_server: str | None = None  # IMAP server
    imap_port: int | None = None  # IMAP port
    use_ssl: bool | None = None  # Use SSL
    imap_folders: str | None = None  # IMAP folders
    imap_state: Any | None = None  # IMAP position
    append_to: str | None = None  # Create documents
    auto_reply: bool | None = None  # Auto-reply
    auto_reply_message: str | None = None  # Auto-reply text
    notify_if_unreplied: bool | None = None  # Notify if not answered
    unreplied_minutes: int | None = None  # Minutes without a reply
    unreplied_group: str | None = None  # Notify group
    signature: str | None = None  # Signature
    reply_to: str | None = None  # Reply-To
    always_bcc: str | None = None  # Always BCC

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
        for field, value in PRESETS.get(self.provider or "", {}).items():
            self.data[field] = value
        if self.auth_method == "OAuth" and not self.connected_app:
            throw(_("Choose the connected app the mailbox signs in through"))

    async def before_save(self) -> None:
        await self._keep_password_when_masked()

    async def after_delete(self) -> None:
        if self.name:
            await disconnect_reference("EmailAccount", self.name)

    # OAuth (grunt.integrations.oauth)

    async def oauth_scopes(self, provider: str | None) -> list[str]:
        return OAUTH_SCOPES.get(provider or "", [])

    async def on_oauth_connected(self, account: str) -> None:
        """Note who allowed access - XOAUTH2 signs in as that account."""
        await self.grunt.db.set_value("EmailAccount", self.name, "oauth_account", account or None)

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
