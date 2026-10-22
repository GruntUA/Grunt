"""Field type enum and DocField model for DocType metadata."""

import functools
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, Literal

from pydantic import BaseModel
from sqlalchemy import JSON as SAJSON
from sqlalchemy import Boolean, Column, Date, Double, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeEngine

from grunt import log
from grunt.db.types import UtcDateTime

# sa_type_name (column_spec's first tuple element) -> SQLAlchemy column type
# builder. Shared by every DocField.to_sa_column() call instead of being
# rebuilt on each one.
_SA_TYPE_BUILDERS: dict[str, Callable[[list[Any]], TypeEngine]] = {
    "String": lambda a: String(a[0]) if a else String(255),
    "Text": lambda a: Text(),
    "Integer": lambda a: Integer(),
    # 8-byte double everywhere - a bare FLOAT is 4-byte (~7 digits) on MySQL.
    "Double": lambda a: Double(),
    # Exact decimal (money). asdecimal=False keeps Python-side values plain floats,
    # so formulas/aggregates/JSON don't have to learn Decimal.
    "Numeric": lambda a: Numeric(*a, asdecimal=False),
    "Boolean": lambda a: Boolean(),
    "Date": lambda a: Date(),
    "DateTime": lambda a: UtcDateTime(),
    "Time": lambda a: Time(),
    # JSONB on Postgres - indexable/queryable; SQLite and MySQL keep plain JSON.
    "JSON": lambda a: SAJSON().with_variant(JSONB(), "postgresql"),
}


# FieldType base class


class FieldType:
    """Base class for all field type implementations.

    Subclass this and set class-level attributes, then call
    ``register_field_type_class(MyFieldType)`` (or define a ``register()``
    function that does so) inside the field type's Python file.

    Override :meth:`parse` for types that need custom value conversion.
    """

    name: ClassVar[str] = ""
    # The column: a tuple ``("String", 255)`` / ``("Double",)``, a callable taking
    # the DocField for sizes that depend on it (see varchar_spec), or None for a
    # type without a column of its own. Read it through column_for().
    column_spec: ClassVar[tuple[Any, ...] | Callable[[Any], tuple[Any, ...]] | None] = None
    searchable: ClassVar[bool] = True
    empty_as_null: ClassVar[bool] = False
    python_type: ClassVar[str] = "Any | None"
    is_layout: ClassVar[bool] = False  # Tab / Section / Column - structure, no value
    # What the rest of the system may assume about this type's value - see TRAITS.
    # Consumers ask has_trait() instead of listing fieldtype names, so a plugin type
    # that declares e.g. "link" gets permissions, fetch_from, relations... for free.
    traits: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def column_for(cls, field: Any) -> tuple[Any, ...] | None:
        """Resolve :attr:`column_spec` for *field* - ``(sa_type_name, *args)`` or None."""
        spec = cls.column_spec
        return spec(field) if callable(spec) else spec

    @classmethod
    def coerce(cls, value: Any) -> Any:
        """Convert a raw input value to the appropriate Python type.

        ``None`` / ``""`` become ``None`` when ``empty_as_null`` is True and are
        kept as is otherwise; anything else goes through :meth:`parse`.
        """
        if value is None or value == "":
            return None if cls.empty_as_null else value
        return cls.parse(value)

    @classmethod
    def parse(cls, value: Any) -> Any:
        """Convert a non-empty raw value. The default keeps it unchanged."""
        return value


# Helpers shared by field type implementations

_MIN_VARCHAR = 64
_MAX_VARCHAR = 1000


def varchar_spec(field: Any) -> tuple[Any, ...]:
    """``column_spec`` for a VARCHAR sized by the field's ``max_length`` (default 255)."""
    return ("String", max(_MIN_VARCHAR, min(field.max_length or 255, _MAX_VARCHAR)))


def parse_float(value: Any) -> Any:
    """``parse`` for float types - a numeric string becomes a float, junk None."""
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return value


def parse_int(value: Any) -> Any:
    """``parse`` for integer types - ``"1.0"`` becomes 1, junk None."""
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return value


# Traits a FieldType may declare. Numeric / date-ness is NOT a trait - it follows
# from column_spec (see is_numeric_fieldtype / is_date_fieldtype).
TRAITS: dict[str, str] = {
    "link": "value is the name of a document of the DocType in `options`",
    "table": "child rows of the DocType in `options`, no column of its own",
    "file": "value is a single file URL",
    "sensitive": "secret - never exported, listed or shown in dashboards",
    "options": "value is one or more of the newline-separated choices in `options`",
    "html": "value is markup sanitized on write (grunt.utils.sanitize) - rendered as is",
}


# Registry

# The FieldType class registry is the single source of truth - column_spec/
# searchable/empty_as_null/python_type are read straight off the registered
# class (falling back to FieldType's own class-level defaults for unknown
# types), instead of mirroring them into parallel dicts that a new FieldType
# attribute would need remembering to also add a dict for.
_FIELD_TYPE_REGISTRY: dict[str, type[FieldType]] = {}


def register_field_type_class(cls: type[FieldType]) -> None:
    """Register a :class:`FieldType` subclass by its ``name`` attribute."""
    unknown = cls.traits - TRAITS.keys()
    if unknown:
        log.warning("field.unknown_traits", fieldtype=cls.name, traits=sorted(unknown))
    _FIELD_TYPE_REGISTRY[cls.name] = cls
    get_storage_class.cache_clear()


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
# change - see get_storage_class().
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


@functools.cache
def get_storage_class(fieldtype: str) -> str:
    """Return the coarse storage class ('text', 'int', ..., 'none') for *fieldtype*.

    Derived from ``column_spec`` - the same source :meth:`DocField.to_sa_column` uses
    to build the real column - so it can't drift from it. ``column_spec`` only needs
    an object with the DocField attributes it reads (e.g. ``max_length``); none of
    them affect the resulting SQLAlchemy type family, so a bare stand-in is enough.
    Consumed by ``grunt fields sync-manifests`` to keep each field type's frontend
    manifest.json in sync instead of that mapping being hand-copied there.
    """
    spec = get_field_type_class(fieldtype).column_for(SimpleNamespace(max_length=None))
    if spec is None:
        return "none"
    return _SA_TYPE_STORAGE_CLASS.get(spec[0], "text")


def get_manifest_attrs(fieldtype: str) -> dict[str, Any]:
    """Backend-owned keys of *fieldtype*'s frontend manifest.json.

    Written by ``grunt fields sync-manifests`` (and checked by a test) so the
    frontend reads the same storage class and traits without a round-trip and
    without them being hand-copied. ``traits`` is left out when there are none.
    """
    attrs: dict[str, Any] = {"storage_class": get_storage_class(fieldtype)}
    traits = get_field_type_class(fieldtype).traits
    if traits:
        attrs["traits"] = sorted(traits)
    return attrs


def is_numeric_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* stores a number (Int, Float, Currency, Duration, ...)."""
    return get_storage_class(fieldtype) in ("int", "float")


def is_date_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* stores a calendar date (Date or Datetime)."""
    return get_storage_class(fieldtype) in ("date", "datetime")


def has_trait(fieldtype: str, trait: str) -> bool:
    """Return True if *fieldtype* declares *trait* (see :data:`TRAITS`)."""
    return trait in get_field_type_class(fieldtype).traits


def fieldtypes_with(trait: str) -> frozenset[str]:
    """Return every registered field type that declares *trait*."""
    return frozenset(name for name, cls in _FIELD_TYPE_REGISTRY.items() if trait in cls.traits)


def is_layout_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* is a layout separator (Tab / Section / Column)."""
    return get_field_type_class(fieldtype).is_layout


def get_python_type(fieldtype: str) -> str:
    """Return the Python type hint string for *fieldtype*.

    Falls back to ``"Any | None"`` for unknown / plugin field types.
    """
    return get_field_type_class(fieldtype).python_type


# Discovery


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
    # The built-in types sit next to the package, wherever the checkout is
    # (a CI runner clones the repo outside any bench).
    scan_paths = [Path(__file__).resolve().parents[2] / "frontend/src/components/fields"]

    bench_dir = _find_bench_dir_for_fields(Path.cwd()) or _find_bench_dir_for_fields(
        Path(__file__).resolve()
    )
    apps_dir = bench_dir / "apps" if bench_dir else None
    if apps_dir and apps_dir.exists():
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
# register() - every field-type module (Select, Link, ...) becomes importable
# and DocField-typeable this way. This has to happen before DocType JSON gets
# parsed anywhere, and every code path that touches DocFields imports this
# module first regardless, so there's no later "real" point to defer it to -
# but it does mean this module can't be imported for its types alone without
# the disk scan, and re-running discovery (e.g. after installing an app at
# runtime) means calling discover_field_types() again explicitly.
discover_field_types()


# Convenience predicates

NON_PHYSICAL_FIELDS: frozenset[str] = frozenset(
    name for name, cls in _FIELD_TYPE_REGISTRY.items() if cls.column_spec is None
)


def is_physical_fieldtype(fieldtype: str) -> bool:
    """Return True if *fieldtype* produces a column in the database."""
    return get_field_type_class(fieldtype).column_spec is not None


def is_empty_as_null_fieldtype(fieldtype: str) -> bool:
    """Return True if an empty string should be coerced to None for *fieldtype*."""
    return get_field_type_class(fieldtype).empty_as_null


# DocField


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
    in_preview: bool = False  # shown in the link hover card (DocType.show_preview_popup)
    bold: bool = False
    # Edit this column inline in the Report (spreadsheet) grid view. Ignored
    # for read-only / layout fields.
    editable_in_grid: bool = False

    # Type-specific options
    options: str | None = None
    # Name of a registry source (see grunt.metadata.dynamic_options) whose
    # registered values replace `options` at schema-serve time - lets Select
    # fields draw their choices from a plugin-extensible registry instead of
    # a static JSON list.
    options_source: str | None = None
    # Select / MultiSelect - show option values through the translation
    # catalog (msgctxt ``select:<DocType>.<field>``). Stored values never change:
    # the served schema carries the translated captions as ``option_labels``.
    # Text fields - values in standard records are extracted for translation
    # (``record:<DocType>.<field>``); readers apply ``translate_record``.
    translatable: bool = False
    # Name of a schema registry source (see grunt.metadata.dynamic_options)
    # whose registered field-lists are attached at schema-serve time as
    # `dynamic_schemas`. `dynamic_schema_key` names the sibling field in the
    # same row/document whose value selects which variant applies - lets a
    # JSON field (typically hidden) render a different form per row instead
    # of a fixed set of columns shared by every variant.
    dynamic_schema_source: str | None = None
    dynamic_schema_key: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    link_filters: str | None = None
    # Link fields only - exclude this field from User Permission row-filtering
    # (see grunt.permissions.user_permissions). Use when a DocType has several
    # Link fields to the same target but only some of them should scope a
    # user's visible rows (e.g. a letter's "registering unit" restricts access
    # while its "sender unit" must stay a free reference).
    ignore_user_permissions: bool = False

    # Layout
    collapsible: bool = False
    show_connections: bool = False  # Tab fields only - host the "Зв'язки" panel in this tab
    columns: int = 12
    icon: str | None = None
    # Tab fields only - mount a bespoke Vue component as the tab body instead of
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
    # (``field__year``) instead of an exact date. None - the date picker.
    quick_filter_mode: Literal["year"] | None = None

    validator: str | None = None

    group_by: str | None = None

    model_config = {"use_enum_values": True}

    def coerce(self, value: Any) -> Any:
        """Convert a raw value to the appropriate Python type for this field."""
        return get_field_type_class(self.fieldtype).coerce(value)

    def has_trait(self, trait: str) -> bool:
        """Return True if this field's type declares *trait* (see :data:`TRAITS`)."""
        return has_trait(self.fieldtype, trait)

    @property
    def is_layout(self) -> bool:
        """Return True if this field is a layout separator (Tab / Section / Column)."""
        return is_layout_fieldtype(self.fieldtype)

    @property
    def is_numeric(self) -> bool:
        """Return True if this field stores a number."""
        return is_numeric_fieldtype(self.fieldtype)

    @property
    def is_date(self) -> bool:
        """Return True if this field stores a calendar date (Date or Datetime)."""
        return is_date_fieldtype(self.fieldtype)

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
        column_spec = get_field_type_class(self.fieldtype).column_for(self)
        if column_spec is None:
            raise ValueError(
                f"Field type '{self.fieldtype}' is virtual"
                if self.is_virtual
                else f"Field type '{self.fieldtype}' is non-physical or has no SA mapping"
            )

        sa_type_name, *args = column_spec
        sa_type = _SA_TYPE_BUILDERS[sa_type_name](args)
        return Column(self.fieldname, sa_type)  # type: ignore[arg-type]
