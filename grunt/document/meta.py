"""Meta class — wrapper over raw DocType metadata (similar to frappe.model.meta.Meta).

Provides convenient access and caching for metadata operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType
    from grunt.metadata.field import DocField


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
        """Return label of the given fieldname or fieldname if not found."""
        f = self._fields_by_name.get(fieldname)
        return f.label if f else fieldname

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
