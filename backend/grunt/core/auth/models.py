"""Auth models — GruntUser Pydantic model (runtime session object backed by User DocType).

Role and UserRole are proper DocTypes managed via grunt.db.
"""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, Field


class GruntUser(BaseModel):
    """Runtime user object populated from the ``User`` DocType.

    Not a SQLAlchemy ORM model — use ``grunt.core.doctypes.User.User``
    helpers to load/create users.
    """

    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    full_name: str = ""
    hashed_password: str = ""
    is_active: bool = True
    is_superadmin: bool = False
    theme: str = "system"
    login_attempts: int = 0
    locked_until: datetime | None = None
    mfa_enabled: bool = False
    mfa_secret: str = ""
    created_at: datetime | None = None
    modified_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)


# Convenience system-user singleton for internal tasks.
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True,
)
