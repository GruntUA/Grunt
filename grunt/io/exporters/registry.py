"""Exporter registry — pluggable document export formats."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.metadata.field import DocField


class Exporter(ABC):
    """Base class for all document exporters.

    Subclass this and register an instance via register_exporter().

    Example (external app)::

        # myapp/mymodule/hooks.py
        from grunt.io import register_exporter
        from myapp.exporters import MyExporter

        io_exporters = [MyExporter()]
    """

    #: Unique format identifier — used in API ``?fmt=`` param and registry lookup.
    id: str

    #: Human-readable label shown in export dialogs.
    label: str

    #: MIME type returned in the HTTP response.
    content_type: str

    #: File extension (without leading dot).
    file_extension: str

    @abstractmethod
    async def export(
        self,
        doctype: str,
        rows: list[dict[str, Any]],
        fields: list[DocField],
    ) -> bytes:
        """Serialize *rows* into bytes.

        Args:
            doctype: DocType name (for sheet titles, metadata, etc.)
            rows:    List of dicts — one dict per document row.
            fields:  Ordered list of DocField objects to include.

        Returns:
            Raw bytes ready to be streamed to the client.
        """

    def filename(self, doctype: str) -> str:
        """Generate a default download filename."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{doctype}_{ts}.{self.file_extension}"


# ── Registry ───────────────────────────────────────────────────────────────

_registry: dict[str, Exporter] = {}


def register_exporter(exp: Exporter) -> None:
    """Register (or replace) an exporter by its id."""
    _registry[exp.id] = exp


def get_exporter(fmt: str) -> Exporter | None:
    """Return the exporter for *fmt*, or None if not found."""
    return _registry.get(fmt)


def get_exporters() -> list[Exporter]:
    """Return all registered exporters in registration order."""
    return list(_registry.values())
