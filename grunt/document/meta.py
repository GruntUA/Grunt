"""Meta class - wrapper over raw DocType metadata.

Provides convenient access and caching for metadata operations.
"""

from collections.abc import Iterable
from typing import Any

from grunt.metadata.compiler import (
    CHILD_COLUMNS,
    STANDARD_COLUMNS,
    compile_doctype_to_table,
    get_table_name,
)
from grunt.metadata.field import DocField, get_field_type_class, get_registered_fieldtypes
from grunt.metadata.permission import DocPermission
lazy from grunt.db.dialects import dialect_for
lazy from grunt.db.schema import DropColumn, diff, read_actual
lazy from grunt.db.schema.apply import apply
lazy from grunt.metadata.doctype import DocType, DocTypeTreeView

# Layout-only fieldtypes that carry no value (FieldType.is_layout). This is the
# base set shared by every "skip non-data fields" filter in the codebase (Meta,
# TS codegen, print fallback rendering); each caller unions in whatever else it
# needs to exclude. Per-field checks should prefer ``DocField.is_layout``.
LAYOUT_FIELDTYPES: frozenset[str] = frozenset(
    name for name in get_registered_fieldtypes() if get_field_type_class(name).is_layout
)


class Meta:
    """Wrapper class for DocType metadata.

    Loads the static DocType from the registry and provides fast access
    to its fields and properties through cached methods.
    """

    # Static properties cache so we don't recalculate multiple times
    _data_fields: list[DocField] | None = None
    _valid_columns: list[str] | None = None
    _columns: frozenset[str] | None = None
    _search_fields: list[str] | None = None
    _physical_fields: list[DocField] | None = None
    _visible_fields: list[DocField] | None = None
    _required_fields: list[DocField] | None = None
    _multilink_fields: list[DocField] | None = None
    _child_table_fields: list[DocField] | None = None
    _table_fieldnames: set[str] | None = None
    _aggregate_fields: list[DocField] | None = None
    _list_view_fields: list[DocField] | None = None
    _numeric_fieldnames: set[str] | None = None
    _searchable_fields: list[DocField] | None = None

    def __init__(self, doctype_obj: DocType) -> None:
        self.doc = doctype_obj
        self._fields_with: dict[str, list[DocField]] = {}
        # Forward direct dot accesses for DocType properties like meta.name, meta.module
        self._fields_by_name = {f.fieldname: f for f in self.doc.fields}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.doc, name)

    # Typed forms of the most used DocType properties (``__getattr__`` answers
    # them too, untyped) - what the permission layer reads (``RoleAccess``).

    @property
    def name(self) -> str:
        """The DocType name."""
        return self.doc.name

    @property
    def permissions(self) -> list[DocPermission]:
        """The DocType's permission rows."""
        return self.doc.permissions

    @property
    def fields(self) -> list[DocField]:
        """The DocType's fields, layout ones included."""
        return self.doc.fields

    @property
    def table_name(self) -> str:
        """Return the physical table name, computing it if not explicitly set."""
        return self.doc.table_name or get_table_name(self.doc.module, self.doc.name)

    @property
    def table(self) -> Any:
        """Return this DocType's compiled :class:`sqlalchemy.Table`.

        Delegates to :func:`compile_doctype_to_table`, which memoizes by
        DocType name - cheap to call repeatedly, kept here for callers that
        already hold a :class:`Meta` and shouldn't need a second import.
        """
        return compile_doctype_to_table(self.doc)

    def get_field(self, fieldname: str) -> DocField | None:
        """Return DocField object if exists, else None."""
        return self._fields_by_name.get(fieldname)

    def has_field(self, fieldname: str) -> bool:
        """Return True if fieldname exists in this DocType."""
        return fieldname in self._fields_by_name

    def get_label(self, fieldname: str) -> str:
        """Return label of the given fieldname, falling back to fieldname itself."""
        f = self._fields_by_name.get(fieldname)
        return (f.label or fieldname) if f else fieldname

    def fields_with(self, trait: str) -> list[DocField]:
        """Return fields whose type declares *trait* (see grunt.metadata.field.TRAITS)."""
        fields = self._fields_with.get(trait)
        if fields is None:
            fields = self._fields_with[trait] = [f for f in self.doc.fields if f.has_trait(trait)]
        return fields

    def get_link_fields(self) -> list[DocField]:
        """Return all fields that link to a document (``link`` trait)."""
        return self.fields_with("link")

    def get_table_fields(self) -> list[DocField]:
        """Return all child table fields (``table`` trait)."""
        return self.fields_with("table")

    def get_data_fields(self) -> list[DocField]:
        """Return data fields (fields that store values)."""
        if self._data_fields is None:
            self._data_fields = [
                f
                for f in self.doc.fields
                if not f.is_layout and f.fieldtype not in ("HTML", "Button")
            ]
        return self._data_fields

    def get_title_field(self) -> str:
        """Return the title field of this doctype."""
        return self.doc.title_field or "name"

    def get_image_field(self) -> str | None:
        """Return the configured image/avatar field, if it names a real field."""
        image_field = self.doc.image_field
        return image_field if image_field and self.has_field(image_field) else None

    def get_tree_view(self) -> DocTypeTreeView | None:
        """Return the tree_view config, or None if this DocType isn't a tree."""
        return self.doc.tree_view

    def get_search_fields(self) -> list[str]:
        """Return the search fields."""
        if self._search_fields is None:
            self._search_fields = self.doc.search_fields.copy() if self.doc.search_fields else []
            if "name" not in self._search_fields:
                self._search_fields.insert(0, "name")
        return self._search_fields

    def get_searchable_fields(self) -> list[DocField]:
        """Return fields whose fieldtype is included in full-text search indexing.

        Not to be confused with :meth:`get_search_fields`, which is the
        DocType's declared ``search_fields`` list (fieldnames shown as a
        result subtitle) rather than a fieldtype-based indexing filter.
        """
        if self._searchable_fields is None:
            self._searchable_fields = [f for f in self.doc.fields if f.is_searchable]
        return self._searchable_fields

    @property
    def columns(self) -> frozenset[str]:
        """The names a stored row holds - the table's columns; for a virtual
        DocType the same names (system ones and physical fields), without
        compiling a table it doesn't have."""
        if self._columns is None:
            if not self.doc.has_table:
                names = [*STANDARD_COLUMNS, *(f.fieldname for f in self.get_physical_fields())]
                if self.doc.is_child:
                    names += CHILD_COLUMNS
                self._columns = frozenset(names)
            else:
                self._columns = frozenset(self.table.c.keys())
        return self._columns

    def get_valid_columns(self) -> list[str]:
        """Return all valid physical database columns - exactly the compiled table's."""
        if self._valid_columns is None:
            self._valid_columns = [c.name for c in self.table.columns]
        return self._valid_columns

    def get_physical_fields(self) -> list[DocField]:
        """Return fields that map to a real database column."""
        if self._physical_fields is None:
            self._physical_fields = [f for f in self.doc.fields if f.is_physical]
        return self._physical_fields

    def get_required_fields(self) -> list[DocField]:
        """Return physical fields marked as required."""
        if self._required_fields is None:
            self._required_fields = [f for f in self.get_physical_fields() if f.required]
        return self._required_fields

    def get_visible_fields(self) -> list[DocField]:
        """Return fields that are not layout-only (Section/Column/Tab) and not hidden."""
        if self._visible_fields is None:
            self._visible_fields = [f for f in self.doc.fields if not f.is_layout and not f.hidden]
        return self._visible_fields

    def get_multilink_fields(self) -> list[DocField]:
        """Return all MultiLink fields."""
        if self._multilink_fields is None:
            self._multilink_fields = [f for f in self.doc.fields if f.fieldtype == "MultiLink"]
        return self._multilink_fields

    def get_child_table_fields(self) -> list[DocField]:
        """Return Table fields that point at a child DocType (options set).

        Unlike :meth:`get_table_fields`, this skips Table fields without
        ``options`` (no child DocType to carry parent linkage, idx, ...).
        """
        if self._child_table_fields is None:
            self._child_table_fields = [f for f in self.get_table_fields() if f.options]
        return self._child_table_fields

    def get_table_fieldnames(self) -> set[str]:
        """Return fieldnames of all child-table (Table) fields."""
        if self._table_fieldnames is None:
            self._table_fieldnames = {f.fieldname for f in self.get_child_table_fields()}
        return self._table_fieldnames

    def get_aggregate_fields(self) -> list[DocField]:
        """Return fields that summarise a child table via aggregate_function."""
        if self._aggregate_fields is None:
            self._aggregate_fields = [f for f in self.doc.fields if f.aggregate_function]
        return self._aggregate_fields

    def get_formula_fields(self, attr: str = "formula") -> list[DocField]:
        """Return fields with a non-empty formula expression under *attr*.

        ``attr`` is ``"formula"`` (computed on save) or ``"read_formula"``
        (computed on read, for virtual fields).
        """
        return [f for f in self.doc.fields if getattr(f, attr, None)]

    def get_numeric_fieldnames(self) -> set[str]:
        """Return fieldnames whose values are numeric (int / float column)."""
        if self._numeric_fieldnames is None:
            self._numeric_fieldnames = {f.fieldname for f in self.doc.fields if f.is_numeric}
        return self._numeric_fieldnames

    def get_list_view_fields(self) -> list[DocField]:
        """Return fields flagged ``in_list_view`` (default report/list columns)."""
        if self._list_view_fields is None:
            self._list_view_fields = [
                f for f in self.doc.fields if getattr(f, "in_list_view", False)
            ]
        return self._list_view_fields

    async def trim_table(
        self,
        engine: Any,
        dry_run: bool = False,
        quiet: bool = False,
        keep: Iterable[str] = (),
    ) -> None:
        """Drop columns from this DocType's database table that are not defined in metadata.

        ``keep`` - columns of other DocTypes stored in the same table (``table_name``),
        which must survive too.
        WARNING: Dropping columns is irreversible and could lead to data loss.
        """
        if not self.doc.has_table:
            return

        table = self.table

        def _trim(connection: Any) -> None:
            actual = read_actual(connection, table.name)
            if actual is None:
                return
            changes = [
                c
                for c in diff(
                    table,
                    actual,
                    sa_dialect=connection.dialect,
                    can_alter_type=True,  # types are not this command's business
                    drop_columns=True,
                    keep=set(keep),
                )
                if isinstance(c, DropColumn)
            ]
            dialect = dialect_for(connection)
            for change in changes:
                if dry_run:
                    if not quiet:
                        print(f"[dry-run] would {change.describe()}")
                    continue
                try:
                    with connection.begin_nested():
                        apply(connection, dialect, [change])
                    if not quiet:
                        print(f"Dropped column '{change.name}' from table '{table.name}'")
                except Exception as e:
                    if not quiet:
                        print(
                            f"Failed to drop column '{change.name}' from table '{table.name}': {e}"
                        )

        async with engine.begin() as conn:
            await conn.run_sync(_trim)
