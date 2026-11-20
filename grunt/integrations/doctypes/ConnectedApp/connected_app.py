"""ConnectedApp - an OAuth client registered at a provider.

Documents get access through it (:mod:`grunt.integrations.oauth`); the
secret, like the tokens, never leaves the server - reads hand out
:data:`~grunt.integrations.oauth.MASK`, and saving it back means "unchanged".
"""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.integrations.oauth import MASK


class ConnectedApp(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Name
    provider: str  # Provider
    enabled: bool | None  # Enabled
    tenant: str | None  # Tenant
    client_id: str  # Client ID
    client_secret: str  # Client secret
    authorization_url: str | None  # Authorization URL
    token_url: str | None  # Token URL
    scopes: str | None  # Extra scopes

    # end: auto-generated types

    async def validate(self) -> None:
        if self.provider == "Other":
            for field in ("authorization_url", "token_url"):
                value = (self.get(field) or "").strip()
                if not value.startswith("https://"):
                    throw(_("The provider addresses must start with https://"))
                self.data[field] = value
        if self.provider == "Microsoft" and not (self.get("tenant") or "").strip():
            self.data["tenant"] = "common"

    async def before_save(self) -> None:
        secret = self.get("client_secret")
        if secret in (MASK, None, "") and self.name:
            self.data["client_secret"] = await self.grunt.db.get_value(
                "ConnectedApp", self.name, "client_secret"
            )
