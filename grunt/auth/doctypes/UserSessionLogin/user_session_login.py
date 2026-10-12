"""UserSessionLogin DocType controller - child table of ``UserSession.logins``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.document.base import Document

if TYPE_CHECKING:
    from datetime import datetime


class UserSessionLogin(Document):
    """One sign-in on a device (a child row of ``UserSession.logins``)."""

    login_at: datetime | None
    ip_address: str | None
    method: str | None
    user_agent: str | None
