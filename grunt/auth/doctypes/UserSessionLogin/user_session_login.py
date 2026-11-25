"""UserSessionLogin DocType controller - child table of ``UserSession.logins``."""

from datetime import datetime

from grunt.document.base import Document


class UserSessionLogin(Document):
    """One sign-in on a device (a child row of ``UserSession.logins``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    login_at: datetime | None = None  # Signed in at
    ip_address: str | None = None  # IP address
    method: str | None = None  # Method
    user_agent: str | None = None  # Browser / client

    # end: auto-generated types
