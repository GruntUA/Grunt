"""Auth models — GruntUser dataclass (backed by User DocType), GruntRole/GruntUserRole system tables."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from grunt.core.db.base import Base


@dataclass
class GruntUser:
    """Runtime user object populated from the ``User`` DocType table (grunt_core_user).

    Not a SQLAlchemy ORM model — use ``auth.service`` helpers to load/create users.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
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
    user_roles: list[GruntUserRole] = field(default_factory=list)

    @property
    def roles(self) -> list[str]:
        return [ur.role_name for ur in self.user_roles]


class GruntRole(Base):
    __tablename__ = "grunt_auth_role"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class GruntUserRole(Base):
    """Maps a user (by id from grunt_core_user) to a role name."""

    __tablename__ = "grunt_auth_user_role"

    # No FK to grunt_core_user — that table is dynamic (DocType-compiled).
    # Integrity is enforced at the application level.
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role_name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("grunt_auth_role.name", ondelete="CASCADE"),
        primary_key=True,
    )
