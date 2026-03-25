"""System DocType definitions — core DocTypes that always exist.

Like Frappe's principle: everything is a DocType, including DocType itself.
These are injected into the registry at startup, their physical tables are
synced, and their document tables are populated from the registry state.
"""

from __future__ import annotations

from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.field import DocField


SYSTEM_DOCTYPES: dict[str, DocType] = {
    "DocType": DocType(
        name="DocType",
        label="Тип документа",
        module="core",
        is_child=False,
        track_changes=False,
        search_fields=["name", "label"],
        title_field="label",
        fields=[
            DocField(
                fieldname="label",
                label="Назва",
                fieldtype="Text",
                in_list_view=True,
                in_filter=False,
                required=True,
            ),
            DocField(
                fieldname="module",
                label="Модуль",
                fieldtype="Text",
                in_list_view=True,
                in_filter=True,
            ),
            DocField(
                fieldname="is_child",
                label="Дочірній",
                fieldtype="Check",
                in_list_view=True,
                in_filter=True,
            ),
        ],
    ),
}


def is_system_doctype(name: str) -> bool:
    """Return True if *name* is a core system DocType."""
    return name in SYSTEM_DOCTYPES
