"""System tables — static SQLAlchemy models for Grunt internals.

Only bootstrap-critical tables that must exist before the DocType registry
loads, plus tables with complex ORM relationships (Workspace), are kept here.

All other system tables (ServerScript, Notification, ActivityLog, etc.) are
now DocType-driven — defined in core/doctypes/*.json.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from grunt.core.db.base import Base


class GruntMetaDoctype(Base):
    """Stores DocType definitions as JSON."""

    __tablename__ = "grunt_meta_doctype"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GruntFile(Base):
    """Uploaded file metadata."""

    __tablename__ = "grunt_files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GruntInstalledApp(Base):
    """Registry of installed Grunt apps."""

    __tablename__ = "grunt_meta_installed_app"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="0.1.0")
    modules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Workspace ────────────────────────────────────────────────────────────────


class GruntRefreshToken(Base):
    """Long-lived refresh tokens (7-day TTL)."""

    __tablename__ = "grunt_refresh_token"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GruntPasswordResetToken(Base):
    """Single-use password reset tokens."""

    __tablename__ = "grunt_password_reset_token"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GruntWorkspace(Base):
    """Workspace — groups sidebar links for an installed app or custom section."""

    __tablename__ = "grunt_workspace"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    app: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="📁")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#2D6A4F")
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    roles: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[GruntWorkspaceLink]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GruntWorkspaceLink.sequence",
    )


class GruntWorkspaceLink(Base):
    """Navigation item inside a workspace sidebar."""

    __tablename__ = "grunt_workspace_link"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("grunt_workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="DocType")
    label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    link_to: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    show_count: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    count_filters: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    show_new_btn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    roles: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped[GruntWorkspace] = relationship(back_populates="items")
