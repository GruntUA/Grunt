"""Field type enum and DocField model for DocType metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from sqlalchemy import Column


import importlib.util
from pathlib import Path

# Core field types (for documentation / reference)
# Plugins can use any string identifier. Built-in types:
#  - Basic: Data, Text, LongText, Int, Float, Check, Date, Datetime, Time, Select
#  - Relations: Link, MultiLink, Table
#  - Media: Attach, Image
#  - Layout: Section, Column, Tab
#  - Special: RichText, JSON, Code, Color, Signature, Geolocation, BarCode


# Global registry for SQLAlchemy column mapping
_SA_TYPE_MAP: dict[str, Any] = {}

# Per-field-type metadata declared at registration time.
# Keys: field type name. Values: dict with "searchable" flag.
_FIELD_META: dict[str, dict[str, Any]] = {}


def register_field_type(name: str, factory: Any, *, searchable: bool = True) -> None:
    """Register a new field type and its SQLAlchemy column factory.

    Args:
        name:       Field type identifier (e.g. ``"Text"``, ``"Image"``).
        factory:    Callable ``(DocField) -> (sa_type_name, *args)`` that
                    returns the SQLAlchemy type spec for the field.
        searchable: Whether the field's value should be included in
                    full-text search indexing.  Set to ``False`` for
                    binary data, structured blobs, or layout-only types.
    """
    _SA_TYPE_MAP[name] = factory
    _FIELD_META[name] = {"searchable": searchable}


def discover_field_types() -> None:
    """Discover and register field types from all apps in the bench.

    Scans every app directory for a 'fields' folder and registers any
    subdirectories that contain a [FieldName].py with a register() function.
    Also scans the frontend components/fields for convenience.
    """
    # Find bench dir: look for apps/ directory in parent chain
    cwd = Path.cwd()
    bench_dir = None
    check = cwd
    for _ in range(5):
        if (check / "apps").is_dir():
            bench_dir = check
            break
        if check == check.parent:
            break
        check = check.parent

    if not bench_dir:
        return

    # 1. Base paths to scan
    scan_paths = [
        bench_dir / "apps/grunt/frontend/src/components/fields",
    ]

    # 2. Scan all app fields
    apps_dir = bench_dir / "apps"
    if apps_dir.exists():
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir():
                continue
            fields_path = app_dir / "fields"
            if fields_path.exists():
                scan_paths.append(fields_path)

    for base_path in scan_paths:
        if not base_path.exists():
            continue

        for field_dir in base_path.iterdir():
            if not field_dir.is_dir():
                continue

            # Look for [FieldName].py (e.g. Text.py inside Text/ folder)
            py_file = field_dir / f"{field_dir.name}.py"
            if py_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"grunt_field_{field_dir.name.lower()}", str(py_file)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "register"):
                            module.register()
                except Exception:
                    # Silent failure to avoid breaking startup
                    pass


# Initialise core mappings
def _init_core_mappings():
    # Discover fields from all apps and core frontend/backend directories
    discover_field_types()


_init_core_mappings()


# Field types that do NOT produce a column in the database.
# These are layout helpers (Section/Column/Tab) or relation containers
# (Table/MultiLink) — they never store a plain value on the document row.
NON_PHYSICAL_FIELDS: frozenset[str] = frozenset({"Section", "Column", "Tab", "Table", "MultiLink"})


class DocField(BaseModel):
    """Single field definition inside a DocType."""

    fieldname: str
    label: str = ""
    fieldtype: str  # Changed from FieldType to str for dynamic discovery

    # Validation
    required: bool = False
    unique: bool = False
    index: bool = False
    read_only: bool = False
    hidden: bool = False

    # Display
    in_list_view: bool = False
    in_filter: bool = False
    bold: bool = False

    # Type-specific options
    options: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    # Layout
    collapsible: bool = False
    columns: int = 12

    # Validation rules
    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None

    # Conditional display
    depends_on: str | None = None
    mandatory_depends_on: str | None = None

    # Formula — Python expression evaluated at save time.
    # Variables: all field values of the document (e.g. ``qty * unit_price``).
    # Built-ins: abs, round, min, max, sum, len, str, int, float, bool.
    # If set, the field is effectively read-only (computed value).
    formula: str | None = None

    model_config = {"use_enum_values": True}

    @property
    def is_searchable(self) -> bool:
        """Return True if this field's value should be included in full-text search.

        Relies on the ``searchable`` flag declared when the field type was
        registered via :func:`register_field_type`.  Non-physical fields
        (layout helpers) are never searchable.  Unknown / plugin field types
        default to ``True`` so they are indexed by default.
        """
        if self.fieldtype in NON_PHYSICAL_FIELDS:
            return False
        meta = _FIELD_META.get(self.fieldtype)
        if meta is not None:
            return meta["searchable"]
        # Unknown field type from a plugin — include in search by default.
        return True

    def to_sa_column(self) -> Column:
        """Return a SQLAlchemy :class:`Column` for this field."""
        from sqlalchemy import (
            JSON as SAJSON,
        )
        from sqlalchemy import (
            Boolean,
            Column,
            Date,
            DateTime,
            Integer,
            String,
            Text,
            Time,
        )
        from sqlalchemy import (
            Float as SAFloat,
        )

        factory = _SA_TYPE_MAP.get(self.fieldtype)
        if factory is None:
            if self.fieldtype in NON_PHYSICAL_FIELDS:
                raise ValueError(f"Field type '{self.fieldtype}' is non-physical")
            raise ValueError(f"Field type '{self.fieldtype}' has no SA mapping")

        spec = factory(self)
        sa_type_name, *args = spec

        _TYPES = {  # noqa: N806
            "String": lambda a: String(a[0]) if a else String(255),
            "Text": lambda a: Text(),
            "Integer": lambda a: Integer(),
            "Float": lambda a: SAFloat(precision=a[0]) if a else SAFloat(),
            "Boolean": lambda a: Boolean(),
            "Date": lambda a: Date(),
            "DateTime": lambda a: DateTime(timezone=True),
            "Time": lambda a: Time(),
            "JSON": lambda a: SAJSON(),
        }
        sa_type = _TYPES[sa_type_name](args)
        return Column(self.fieldname, sa_type)  # type: ignore[arg-type]
