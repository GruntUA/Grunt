"""UserSessionLogin DocType controller - child table of ``UserSession.logins``."""

from datetime import datetime

from grunt.document.base import Document


class UserSessionLogin(Document):
    """One sign-in on a device (a child row of ``UserSession.logins``)."""

    login_at: datetime | None
    ip_address: str | None
    method: str | None
    user_agent: str | None
