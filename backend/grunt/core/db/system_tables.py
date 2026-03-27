"""System tables — static SQLAlchemy models for Grunt internals.

These tables are NOT DocType-driven — they are defined as regular ORM models.
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


class GruntLogActivity(Base):
    """Activity log for workflow transitions and other document events."""

    __tablename__ = "grunt_log_activity"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    doctype: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    user: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class GruntPage(Base):
    """Custom page registrations from installed apps."""

    __tablename__ = "grunt_page"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    route: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    component: Mapped[str] = mapped_column(String(255), nullable=False)
    app: Mapped[str] = mapped_column(String(100), nullable=False)
    sidebar_section: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sidebar_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default_home: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GruntReport(Base):
    """Stored report definitions."""

    __tablename__ = "grunt_report"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    report_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Query|Script|List
    doctype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    columns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    filters_config: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Workspace ────────────────────────────────────────────────────────────────


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


# ── Print Formats ─────────────────────────────────────────────────────────────


class GruntPrintFormat(Base):
    """Custom print format templates for document generation."""

    __tablename__ = "grunt_print_format"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    template_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="html"
    )  # html, docx
    template: Mapped[str] = mapped_column(Text, nullable=False)  # Jinja2 HTML or DOCX path
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Translations ──────────────────────────────────────────────────────────────


class GruntTranslation(Base):
    """User/app-supplied translations for i18n."""

    __tablename__ = "grunt_translation"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    translated: Mapped[str] = mapped_column(String(1000), nullable=False)
    context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Naming Series ─────────────────────────────────────────────────────────────


class GruntNamingSeries(Base):
    """Counter storage for pattern-based autoname (e.g. INV-.YYYY.-.####)."""

    __tablename__ = "grunt_naming_series"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    prefix: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ── Document Versioning ───────────────────────────────────────────────────────


class GruntDocVersion(Base):
    """Stores JSON diff of every document change for version history."""

    __tablename__ = "grunt_doc_version"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    doc_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    user: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Notifications ─────────────────────────────────────────────────────────────


class GruntNotificationRule(Base):
    """Defines when notifications should be sent."""

    __tablename__ = "grunt_notification_rule"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # after_insert, after_save, on_transition, value_change
    channel: Mapped[str] = mapped_column(
        String(50), nullable=False, default="system"
    )  # system, email, both
    recipients: Mapped[str] = mapped_column(
        String(1000), nullable=False, default=""
    )  # comma-separated: "owner", "role:Manager", "user@example.com"
    condition: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Python expression: "doc.get('status') == 'Overdue'"
    subject_template: Mapped[str] = mapped_column(
        String(500), nullable=False, default="{doctype}: {name}"
    )
    message_template: Mapped[str] = mapped_column(
        Text, nullable=False, default="{doctype} {name} was {event}"
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GruntNotification(Base):
    """Individual notification sent to a user."""

    __tablename__ = "grunt_notification"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    doctype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── Scripting ────────────────────────────────────────────────────────────────


class GruntServerScript(Base):
    """Server-side Python scripts executed on document events or as API endpoints."""

    __tablename__ = "grunt_server_script"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    script_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # DocType Event, API, Scheduler Event
    doctype: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    event: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # before_insert, after_save, etc.
    api_method: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )  # for API type: /api/method/{api_method}
    cron: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # for Scheduler type: "0 */6 * * *"
    script: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_guest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GruntClientScript(Base):
    """Client-side JavaScript injected into the frontend for specific DocTypes."""

    __tablename__ = "grunt_client_script"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    script: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Web Forms ────────────────────────────────────────────────────────────────


class GruntWebForm(Base):
    """Public web form for anonymous or authenticated submissions."""

    __tablename__ = "grunt_web_form"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    route: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    introduction: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_message: Mapped[str] = mapped_column(
        String(1000), nullable=False, default="Дякуємо! Вашу заявку прийнято."
    )
    success_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allow_edit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    login_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_submissions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submit_label: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Надіслати"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ── Document Links ───────────────────────────────────────────────────────────


class GruntDocLink(Base):
    """Automatic backlink between documents created from Link fields."""

    __tablename__ = "grunt_doc_link"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Source document (the one containing the Link field)
    source_doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Target document (the one being linked to)
    target_doctype: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    link_fieldname: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

