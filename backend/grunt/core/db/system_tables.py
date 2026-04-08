"""System tables — static SQLAlchemy models for Grunt internals.

Only bootstrap-critical tables that must exist before the DocType registry
loads, plus tables with complex ORM relationships (Workspace), are kept here.

All other system tables (ServerScript, Notification, ActivityLog, etc.) are
now DocType-driven — defined in core/doctypes/*.json.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
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


