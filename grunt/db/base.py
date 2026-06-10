"""Base SQLAlchemy model with common columns."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Abstract base for all ORM models."""

    pass


class GruntBase(Base):
    """Common columns shared by every Grunt system table.

    Provides: name (string PK), created_at, modified_at, modified_by.
    """

    __abstract__ = True

    name: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    modified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
