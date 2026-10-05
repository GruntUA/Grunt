"""Field type enum and DocField model for DocType metadata."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel
from sqlalchemy import JSON as SAJSON
from sqlalchemy import Boolean, Column, Date, Double, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB

from grunt import log
from grunt.db.types import UtcDateTime

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.types import TypeEngine


# sa_type_name (column_spec's first tuple element) -> SQLAlchemy column type
# builder. Shared by every DocField.to_sa_column() call instead of being
# rebuilt on each one.
_SA_TYPE_BUILDERS: dict[str, Callable[[list[Any]], TypeEngine]] = {
    "String": lambda a: String(a[0]) if a else String(255),
    "Text": lambda a: Text(),
    "Integer": lambda a: Integer(),
    # 8-byte double everywhere — a bare FLOAT is 4-byte (~7 digits) on MySQL.
    "Double": lambda a: Double(),
    # Exact decimal (money). asdecimal=False keeps Python-side values plain floats,
    # so formulas/aggregates/JSON don't have to learn Decimal.
    "Numeric": lambda a: Numeric(*a, asdecimal=False),
    "Boolean": lambda a: Boolean(),
    "Date": lambda a: Date(),
    "DateTime": lambda a: UtcDateTime(),
    "Time": lambda a: Time(),
    # JSONB on Postgres — indexable/queryable; SQLite and MySQL keep plain JSON.
    "JSON": lambda a: SAJSON().with_variant(JSONB(), "postgresql"),
}


# ── FieldType base class ──────────────────────────────────────────────────────


class FieldType:
    """Base class for all field type implementations.

    Subclass this and set class-level attributes, then call
    ``register_field_type_class(MyFieldType)`` (or define a ``register()``
    function that does so) inside the field type's Python file.

    Override :meth:`coerce` for types that need custom value conversion.
    """

    name: ClassVar[str] = ""
    column_spec: ClassVar[Any] = None  # Callable[[DocField], tuple] | None
    searchable: ClassVar[bool] = True
    empty_as_null: ClassVar[bool] = False
    python_type: ClassVar[str] = "Any | None"

    @classmethod
    def coerce(cls, value: Any) -> Any:
        """Convert a raw input value to the appropriate Python type.

        The default implementation converts ``None`` / ``""`` to ``None``
        when ``empty_as_null`` is True, and returns the value unchanged
        otherwise.  Subclasses override this for numeric, date, and other
        types that need explicit parsing.
        """
        if value is None or value == "":
            return None if cls.empty_as_null else value
        return value


# ── Registry ──────────────────────────────────────────────────────────────────

# The FieldType class registry is the single source of truth — column_spec/
# searchable/empty_as_null/python_type are read straight off the registered
# class (falling back to FieldType's own class-level defaults for unknown
# types), instead of mirroring them into parallel dicts that a new FieldType
# attribute would need remembering to also add a dict for.
_FIELD_TYPE_REGISTRY: dict[str, type[FieldType]] = {}


def register_field_type_class(cls: type[FieldType]) -> None:
    """Register a :class:`FieldType` subclass by its ``name`` attribute."""
    _FIELD_TYPE_REGISTRY[cls.name] = cls


def get_field_type_class(fieldtype: str) -> type[FieldType]:
    """Return the :class:`FieldType` subclass for *fieldtype*.

    Falls back to the base :class:`FieldType` for unknown / plugin types.
    """
    return _FIELD_TYPE_REGISTRY.get(fieldtype, FieldType)


def get_registered_fieldtypes() -> list[str]:
    """Return every registered field type name, in registration order."""
    return list(_FIELD_TYPE_REGISTRY.keys())


# column_spec's first tuple element (the SQLAlchemy type family) collapsed to the
# coarse storage class the DocType «Конструктор» warns about on a fieldtype
# change — see get_storage_class().
_SA_TYPE_STORAGE_CLASS: dict[str, str] = {
    "String": "text",
    "Text": "text",
    "Integer": "int",
    "Double": "float",
    "Numeric": "float",
    "Boolean": "bool",
    "Date": "date",
    "DateTime": "datetime",
    "Time": "time",
    "JSON": "json",
}


def get_storage_class(fieldtype: str) -> str:
    """Return the coarse storage class ('text', 'int', ..., 'none') for *fieldtype*.

    Derived from ``column_spec`` — the same source :meth:`DocField.to_sa_column` uses
    to build the real column — so it can't drift from it. ``column_spec`` only needs
    an object with the DocField attributes it reads (e.g. ``max_length``); none of
    them affect the resulting SQLAlchemy type family, so a bare stand-in is enough.
    Consumed by ``grunt fields sync-manifests`` to keep each field type's frontend
    manifest.json in sync instead of that mapping being hand-copied there.
    """
    cls = get_field_type_class(fieldtype)
    if cls.column_spec is None:
        return "none"
    sa_type_name = cls.column_spec(SimpleNamespace(max_length=None))[0]
    return _SA_TYPE_STORAGE_CLASS.get(sa_type_name, "text")


def get_python_type(fieldtype: str) -> str:
    """Return the Python type hint string for *fieldtype*.

    Falls back to ``"Any | None"`` for unknown / plugin field types.
    """
    return get_field_type_class(fieldtype).python_type


# ── Discovery ─────────────────────────────────────────────────────────────────


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
    bench_dir = _find_bench_dir_for_fields(Path.cwd()) or _find_bench_dir_for_fields(
        Path(__file__).resolve()
    )
    if not bench_dir:
        return

    scan_paths = [
        bench_dir / "apps/grunt/frontend/src/components/fields",
    ]

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
                    log.exception("suppressed_error")


# Runs once, as an import-time side effect: plain `import grunt.metadata.field`
# scans every app's fields/ dir on disk and dynamically loads each plugin's
# register() — every field-type module (Select, Link, ...) becomes importable
# and DocField-typeable this way. This has to happen before DocType JSON gets
# parsed anywhere, and every code path that touches DocFields imports this
# module first regardless, so there's no later "real" point to defer it to —
# but it does mean this module can't be imported for its types alone without
# the disk scan, and re-running discovery (e.g. after installing an app at
# runtime) means calling discover_field_types() again explicitly.
discover_field_types()


# ── Convenience predicates ────────────────────────────────────────────────────

NON_PHYSICAL_FIELDS: frozenset[str] = frozenset(
    name for name, cls in _FIELD_TYPE_REGISTRY.items() if cls.column_spec is None
)


def is_physical_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* produces a column in the database."""
    return get_field_type_class(fieldtype).column_spec is not None


def is_empty_as_null_fieldtype(fieldtype: str) -> bool:
    """Return True if an empty string should be coerced to None for *fieldtype*."""
    return get_field_type_class(fieldtype).empty_as_null


# ── DocField ──────────────────────────────────────────────────────────────────


class DocField(BaseModel):
    """Single field definition inside a DocType."""

    fieldname: str
    label: str = ""
    fieldtype: str

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
    # Edit this column inline in the Report (spreadsheet) grid view. Ignored
    # for read-only / layout fields.
    editable_in_grid: bool = False

    # Type-specific options
    options: str | None = None
    # Name of a registry source (see grunt.metadata.dynamic_options) whose
    # registered values replace `options` at schema-serve time — lets Select
    # fields draw their choices from a plugin-extensible registry instead of
    # a static JSON list.
    options_source: str | None = None
    # Select / MultiSelect only — show option values through the translation
    # catalog (msgctxt ``select:<DocType>.<field>``). Stored values never change:
    # the served schema carries the translated captions as ``option_labels``.
    translatable: bool = False
    # Name of a schema registry source (see grunt.metadata.dynamic_options)
    # whose registered field-lists are attached at schema-serve time as
    # `dynamic_schemas`. `dynamic_schema_key` names the sibling field in the
    # same row/document whose value selects which variant applies — lets a
    # JSON field (typically hidden) render a different form per row instead
    # of a fixed set of columns shared by every variant.
    dynamic_schema_source: str | None = None
    dynamic_schema_key: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    link_filters: str | None = None
    # Link fields only — exclude this field from User Permission row-filtering
    # (see grunt.permissions.user_permissions). Use when a DocType has several
    # Link fields to the same target but only some of them should scope a
    # user's visible rows (e.g. a letter's "registering unit" restricts access
    # while its "sender unit" must stay a free reference).
    ignore_user_permissions: bool = False

    # Layout
    collapsible: bool = False
    show_connections: bool = False  # Tab fields only — host the "Зв'язки" panel in this tab
    columns: int = 12
    icon: str | None = None
    # Tab fields only — mount a bespoke Vue component as the tab body instead of
    # the generic section/field layout (e.g. "DesignerTab", "WorkflowGraphTab").
    tab_component: str | None = None

    # Validation rules
    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None

    # Conditional display
    depends_on: str | None = None
    mandatory_depends_on: str | None = None

    formula: str | None = None

    aggregate_function: str | None = None
    aggregate_table: str | None = None
    aggregate_field: str | None = None

    is_virtual: bool = False
    read_formula: str | None = None

    fetch_from: str | None = None

    in_quick_entry: bool = False
    in_quick_filter: bool = False
    # Date/Datetime quick filters only: "year" picks a calendar year
    # (``field__year``) instead of an exact date. None — the date picker.
    quick_filter_mode: Literal["year"] | None = None

    validator: str | None = None

    group_by: str | None = None

    model_config = {"use_enum_values": True}

    def coerce(self, value: Any) -> Any:
        """Convert a raw value to the appropriate Python type for this field."""
        return get_field_type_class(self.fieldtype).coerce(value)

    @property
    def is_physical(self) -> bool:
        """Return True if this field stores a value in a database column."""
        return is_physical_fieldtype(self.fieldtype) and not self.is_virtual

    @property
    def empty_as_null(self) -> bool:
        """Return True if an empty string should be coerced to None for this field."""
        return get_field_type_class(self.fieldtype).empty_as_null

    @property
    def is_searchable(self) -> bool:
        """Return True if this field's value should be included in full-text search."""
        if not is_physical_fieldtype(self.fieldtype):
            return False
        return get_field_type_class(self.fieldtype).searchable

    def to_sa_column(self) -> Column:
        """Return a SQLAlchemy :class:`Column` for this field."""
        column_spec = get_field_type_class(self.fieldtype).column_spec
        if column_spec is None:
            raise ValueError(
                f"Field type '{self.fieldtype}' is virtual"
                if self.is_virtual
                else f"Field type '{self.fieldtype}' is non-physical or has no SA mapping"
            )

        sa_type_name, *args = column_spec(self)
        sa_type = _SA_TYPE_BUILDERS[sa_type_name](args)
        return Column(self.fieldname, sa_type)  # type: ignore[arg-type]
