"""Importer registry — pluggable document import formats."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Importer(ABC):
    """Base class for all document importers.

    Subclass this and register an instance via register_importer().

    Example (external app)::

        # myapp/mymodule/hooks.py
        from grunt.io import register_importer
        from myapp.importers import MyImporter

        io_importers = [MyImporter()]
    """

    #: Unique format identifier (e.g. ``'csv'``, ``'xlsx'``).
    id: str

    #: Human-readable label.
    label: str

    #: File extensions this importer accepts (without leading dot).
    accepted_extensions: list[str]

    @abstractmethod
    def read(
        self,
        file_path: Path,
        limit: int | None = None,
    ) -> list[list[Any]]:
        """Read *file_path* and return rows as a list of lists.

        The first row must be the header row.

        Args:
            file_path: Absolute path to the uploaded file.
            limit:     Optional row cap (including the header row).

        Returns:
            ``[[header1, header2, ...], [val1, val2, ...], ...]``
        """

    def accepts(self, filename: str) -> bool:
        """Return True if this importer handles *filename* by extension."""
        ext = Path(filename).suffix.lstrip(".").lower()
        return ext in [e.lower() for e in self.accepted_extensions]


# ── Registry ───────────────────────────────────────────────────────────────

_registry: dict[str, Importer] = {}


def register_importer(imp: Importer) -> None:
    """Register (or replace) an importer by its id."""
    _registry[imp.id] = imp


def get_importer(fmt: str) -> Importer | None:
    """Return the importer for *fmt*, or None if not found."""
    return _registry.get(fmt)


def get_importers() -> list[Importer]:
    """Return all registered importers in registration order."""
    return list(_registry.values())


def get_importer_for_file(filename: str) -> Importer | None:
    """Auto-detect the right importer from the file extension."""
    for imp in _registry.values():
        if imp.accepts(filename):
            return imp
    return None
