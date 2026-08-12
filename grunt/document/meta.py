"""Meta class — wrapper over raw DocType metadata (similar to frappe.model.meta.Meta).

Provides convenient access and caching for metadata operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType
    from grunt.metadata.field import DocField

# Fieldtypes whose values are treated as numbers in formula/expression contexts.
NUMERIC_FIELDTYPES: frozenset[str] = frozenset({"Int", "Float", "Currency", "Percent"})

# Layout-only fieldtypes that carry no value (used to build "visible" field lists).
_LAYOUT_FIELDTYPES: frozenset[str] = frozenset({"Section", "Column", "Tab"})


class Meta:
    """Wrapper class for DocType metadata.

    Loads the static DocType from the registry and provides fast access
    to its fields and properties through cached methods.
    """

    # Static properties cache so we don't recalculate multiple times
    _table_fields: list[DocField] | None = None
    _link_fields: list[DocField] | None = None
    _data_fields: list[DocField] | None = None
    _valid_columns: list[str] | None = None
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

    def __init__(self, doctype_obj: DocType) -> None:
        self.doc = doctype_obj
        # Forward direct dot accesses for DocType properties like meta.name, meta.module
        self._fields_by_name = {f.fieldname: f for f in self.doc.fields}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.doc, name)

    @property
    def table_name(self) -> str:
        """Return the physical table name, computing it if not explicitly set."""
        from grunt.metadata.compiler import get_table_name

        return self.doc.table_name or get_table_name(self.doc.module, self.doc.name)

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

    def get_link_fields(self) -> list[DocField]:
        """Return all Link and Dynamic Link fields."""
        if self._link_fields is None:
            self._link_fields = [
                f for f in self.doc.fields if f.fieldtype in ("Link", "Dynamic Link")
            ]
        return self._link_fields

    def get_table_fields(self) -> list[DocField]:
        """Return all child table fields (Table, Table MultiSelect)."""
        if self._table_fields is None:
            self._table_fields = [
                f for f in self.doc.fields if f.fieldtype in ("Table", "Table MultiSelect")
            ]
        return self._table_fields

    def get_data_fields(self) -> list[DocField]:
        """Return data fields (fields that store values)."""
        if self._data_fields is None:
            ui_fieldtypes = {"Section", "Column", "HTML", "Tab", "Tab Break", "Button"}
            self._data_fields = [f for f in self.doc.fields if f.fieldtype not in ui_fieldtypes]
        return self._data_fields

    def get_title_field(self) -> str:
        """Return the title field of this doctype."""
        return self.doc.title_field or "name"

    def get_search_fields(self) -> list[str]:
        """Return the search fields."""
        if self._search_fields is None:
            self._search_fields = self.doc.search_fields.copy() if self.doc.search_fields else []
            if "name" not in self._search_fields:
                self._search_fields.insert(0, "name")
        return self._search_fields

    def get_valid_columns(self) -> list[str]:
        """Return all valid physical database columns."""
        if self._valid_columns is None:
            cols = [
                "id",
                "name",
                "owner",
                "created_at",
                "modified_at",
                "docstatus",
                "idx",
                "parent",
                "parentfield",
                "parenttype",
            ]
            sys_cols = set(cols)

            for df in self.doc.fields:
                if df.is_physical and df.fieldname not in sys_cols:
                    cols.append(df.fieldname)
            self._valid_columns = cols
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
            self._visible_fields = [
                f for f in self.doc.fields if f.fieldtype not in _LAYOUT_FIELDTYPES and not f.hidden
            ]
        return self._visible_fields

    def get_multilink_fields(self) -> list[DocField]:
        """Return all MultiLink fields."""
        if self._multilink_fields is None:
            self._multilink_fields = [f for f in self.doc.fields if f.fieldtype == "MultiLink"]
        return self._multilink_fields

    def get_child_table_fields(self) -> list[DocField]:
        """Return Table fields that point at a child DocType (options set).

        Unlike :meth:`get_table_fields`, this excludes "Table MultiSelect"
        fields, which don't carry child-row semantics (parent linkage, idx, ...).
        """
        if self._child_table_fields is None:
            self._child_table_fields = [
                f for f in self.doc.fields if f.fieldtype == "Table" and f.options
            ]
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
        """Return fieldnames whose values are numeric (Int/Float/Currency/Percent)."""
        if self._numeric_fieldnames is None:
            self._numeric_fieldnames = {
                f.fieldname for f in self.doc.fields if f.fieldtype in NUMERIC_FIELDTYPES
            }
        return self._numeric_fieldnames

    def get_list_view_fields(self) -> list[DocField]:
        """Return fields flagged ``in_list_view`` (default report/list columns)."""
        if self._list_view_fields is None:
            self._list_view_fields = [
                f for f in self.doc.fields if getattr(f, "in_list_view", False)
            ]
        return self._list_view_fields

    async def trim_table(self, engine: Any, dry_run: bool = False, quiet: bool = False) -> None:
        """Drop columns from this DocType's database table that are not defined in metadata.
        WARNING: Dropping columns is irreversible and could lead to data loss.
        """
        if self.doc.is_virtual:
            return

        from sqlalchemy import inspect, text

        from grunt.metadata.compiler import get_table_name

        table_name = self.doc.table_name or get_table_name(self.doc.module, self.doc.name)

        def _trim(connection):
            insp = inspect(connection)

            if not insp.has_table(table_name):
                return

            db_cols = {c["name"] for c in insp.get_columns(table_name)}
            valid_cols = set(self.get_valid_columns())

            to_drop = db_cols - valid_cols

            for col in to_drop:
                if dry_run:
                    if not quiet:
                        print(f"[dry-run] would DROP COLUMN '{col}' from TABLE '{table_name}'")
                else:
                    try:
                        connection.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN "{col}"'))
                        if not quiet:
                            print(f"Dropped column '{col}' from table '{table_name}'")
                    except Exception as e:
                        if not quiet:
                            print(f"Failed to drop column '{col}' from table '{table_name}': {e}")

        async with engine.begin() as conn:
            await conn.run_sync(_trim)
