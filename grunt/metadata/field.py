"""Field type enum and DocField model for DocType metadata."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()
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

# Python type hint string per field type (used by code scaffold).
_PYTHON_TYPE_MAP: dict[str, str] = {}


def register_field_type(
    name: str,
    factory: Any | None,
    *,
    searchable: bool = True,
    python_type: str = "Any | None",
) -> None:
    """Register a new field type and its SQLAlchemy column factory.

    Args:
        name:        Field type identifier (e.g. ``"Text"``, ``"Image"``).
        factory:     Callable ``(DocField) -> (sa_type_name, *args)`` that
                     returns the SQLAlchemy type spec for the field.
                     Pass ``None`` for non-physical types (e.g. MultiLink)
                     that have no database column.
        searchable:  Whether the field's value should be included in
                     full-text search indexing.  Set to ``False`` for
                     binary data, structured blobs, or layout-only types.
        python_type: Python type hint string used when scaffolding
                     controller code (e.g. ``"str | None"``).
    """
    if factory is not None:
        _SA_TYPE_MAP[name] = factory
    _FIELD_META[name] = {"searchable": searchable}
    _PYTHON_TYPE_MAP[name] = python_type


def get_python_type(fieldtype: str) -> str:
    """Return the Python type hint string for *fieldtype*.

    Falls back to ``"Any | None"`` for unknown / plugin field types.
    """
    return _PYTHON_TYPE_MAP.get(fieldtype, "Any | None")


def _find_bench_dir_for_fields(start: Path) -> Path | None:
    """Walk up from *start* looking for a directory that contains apps/."""
    check = start if start.is_dir() else start.parent
    for _ in range(8):
        if (check / "apps").is_dir():
            return check
        if check == check.parent:
            break
        check = check.parent
    return None


def discover_field_types() -> None:
    """Discover and register field types from all apps in the bench.

    Scans every app directory for a 'fields' folder and registers any
    subdirectories that contain a [FieldName].py with a register() function.
    Also scans the frontend components/fields for convenience.
    """
    # Find bench dir: first try cwd, then fall back to package location
    bench_dir = _find_bench_dir_for_fields(Path.cwd()) or _find_bench_dir_for_fields(
        Path(__file__).resolve()
    )
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
                    logger.exception("suppressed_error")


# Initialise core mappings
def _init_core_mappings():
    # Discover fields from all apps and core frontend/backend directories
    discover_field_types()


_init_core_mappings()


# Field types that do NOT produce a column in the database.
# Computed from the registry: any registered type without an SA factory is non-physical.
# Layout helpers (Section/Column/Tab), relation containers (Table/MultiLink) and
# display-only types (HTML, Button, Heading, …) all fall into this category.
NON_PHYSICAL_FIELDS: frozenset[str] = frozenset(ft for ft in _FIELD_META if ft not in _SA_TYPE_MAP)


def is_physical_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* produces a column in the database.

    This is the single source of truth for physical vs. non-physical fields.
    A field type is physical when it was registered with a non-None SA factory
    via :func:`register_field_type`.  Layout helpers (Section, Column, Tab),
    relation containers (Table, MultiLink) and display-only types (HTML,
    Button, Heading …) return False.

    Unknown / unregistered field types also return False (safe default).
    """
    return fieldtype in _SA_TYPE_MAP


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

    # Link field — optional filters for the link_search dropdown.
    # JSON object: '{"status": "Active"}' or expression 'eval: {"company": doc.company}'.
    link_filters: str | None = None

    # Layout
    collapsible: bool = False
    columns: int = 12
    icon: str | None = None
    experimental_component: str | None = None

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

    # Aggregation — computes a summary value from a child TABLE field.
    # aggregate_function: "sum" | "count" | "avg" | "min" | "max"
    # aggregate_table:    fieldname of the TABLE field in this DocType
    # aggregate_field:    fieldname in the child DocType to aggregate (not needed for "count")
    aggregate_function: str | None = None
    aggregate_table: str | None = None
    aggregate_field: str | None = None

    # Virtual — field has no physical column, calculated on read via read_formula.
    is_virtual: bool = False
    read_formula: str | None = None

    # Dashboard — show this field as a badge at the top of the form.
    # dashboard_doctype: if set, adds a "+" button to create new records of this type.
    show_in_dashboard: bool = False
    dashboard_doctype: str | None = None
    # The fieldname in dashboard_doctype that links back here (used for:
    # 1) pre-filling on create, 2) filtering the list view)
    dashboard_link_field: str | None = None

    # Fetch From — automatically populate value from a linked document.
    # Format: "link_fieldname.field_to_fetch" (e.g., "customer.name")
    fetch_from: str | None = None

    # Quick Entry — show this field in the quick-entry dialog.
    # If False, field is only shown when quick_entry shows required fields.
    in_quick_entry: bool = False
    # Quick Filter — show this field in list quick filters bar.
    in_quick_filter: bool = False

    # Named validator — runs at save time (e.g. "email", "phone", "url", "iban_ua").
    # Custom validators can be registered via grunt.document.validators.register_validator().
    validator: str | None = None

    # Table field — group child rows by this fieldname of the child DocType.
    # When set, the Table component renders a subheader row for each distinct value.
    group_by: str | None = None

    model_config = {"use_enum_values": True}

    @property
    def is_physical(self) -> bool:
        """Return True if this field stores a value in a database column.

        A field is physical when its type has a registered SA factory *and*
        it is not marked as virtual.  Use this as the canonical check instead
        of comparing against hardcoded field-type sets.
        """
        return is_physical_fieldtype(self.fieldtype) and not self.is_virtual

    @property
    def is_searchable(self) -> bool:
        """Return True if this field's value should be included in full-text search.

        Relies on the ``searchable`` flag declared when the field type was
        registered via :func:`register_field_type`.  Non-physical fields
        (layout helpers) are never searchable.  Unknown / plugin field types
        default to ``True`` so they are indexed by default.
        """
        if not is_physical_fieldtype(self.fieldtype):
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
            raise ValueError(
                f"Field type '{self.fieldtype}' is virtual"
                if self.is_virtual
                else f"Field type '{self.fieldtype}' is non-physical or has no SA mapping"
            )

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
