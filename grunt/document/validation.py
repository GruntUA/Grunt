"""Validation and type coercion for Documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.document.validators import validate_field_value
from grunt.metadata.field import get_field_type_class, is_physical_fieldtype

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType


def _validate_data(
    doctype: DocType,
    data: dict[str, Any],
    partial: bool = False,
    ignore_required: bool = False,
) -> list[str]:
    """Validate document data against DocType fields."""
    errors: list[str] = []
    for field in doctype.fields:
        if not is_physical_fieldtype(field.fieldtype):
            continue

        value = data.get(field.fieldname)

        if field.required and not ignore_required:
            if partial and field.fieldname not in data:
                continue
            if (value is None or value == "") and field.default is None:
                errors.append(f"{field.fieldname}: Поле '{field.label}' є обов'язковим")

        if field.validator and value is not None and value != "":
            error = validate_field_value(
                field.validator, str(value), field.label or field.fieldname
            )
            if error:
                errors.append(f"{field.fieldname}: {error}")

        if value is not None and value != "":
            column_spec = get_field_type_class(field.fieldtype).column_spec
            if column_spec is not None:
                sa_type_name, *args = column_spec(field)
                # SQLite doesn't enforce VARCHAR length — check it ourselves so a
                # value that "fits" in dev doesn't fail only once deployed on
                # Postgres/MySQL, where VARCHAR(n) is a hard limit.
                if sa_type_name == "String" and args and len(str(value)) > args[0]:
                    errors.append(
                        f"{field.fieldname}: Поле '{field.label}' занадто довге "
                        f"(максимум {args[0]} символів)"
                    )

    return errors
