"""Auth SQLAlchemy models — User, Role, UserRole."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grunt.core.db.base import Base


class GruntUser(Base):
    __tablename__ = "grunt_auth_user"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user_roles: Mapped[list[GruntUserRole]] = relationship(
        back_populates="user", lazy="selectin"
    )

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
    __tablename__ = "grunt_auth_user_role"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("grunt_auth_user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_name: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("grunt_auth_role.name", ondelete="CASCADE"),
        primary_key=True,
    )

    user: Mapped[GruntUser] = relationship(back_populates="user_roles")
