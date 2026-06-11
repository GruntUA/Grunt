"""System tables — Core SQLAlchemy Table definitions for Grunt internals.

Only bootstrap-critical tables that must exist before the DocType registry
loads are kept here.

All other system tables (ServerScript, Notification, ActivityLog, etc.) are
DocType-driven — defined in core/doctypes/*.json.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Integer, String, Table, func, text

from grunt.db.base import metadata

GruntMetaDoctype = Table(
    "grunt_meta_doctype",
    metadata,
    Column("name", String(255), primary_key=True),
    Column("module", String(255), nullable=False),
    Column("data", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("modified_at", DateTime(timezone=True), server_default=func.now()),
)

GruntInstalledApp = Table(
    "grunt_meta_installed_app",
    metadata,
    Column("name", String(100), primary_key=True),
    Column("title", String(255), nullable=False),
    Column("version", String(50), nullable=False, server_default=text("'0.1.0'")),
    Column("modules", JSON, nullable=False, server_default=text("'[]'")),
    Column("owner", String(255), nullable=False, server_default=text("'system'")),
    Column("docstatus", Integer, server_default=text("0")),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("modified_at", DateTime(timezone=True), server_default=func.now()),
    Column("modified_by", String(255), nullable=True),
    Column("installed_at", DateTime(timezone=True), server_default=func.now()),
)
