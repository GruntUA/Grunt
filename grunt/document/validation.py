"""Validation and type coercion for Documents."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from grunt import _, log
from grunt.document.validators import validate_field_value
from grunt.metadata.field import get_field_type_class, is_physical_fieldtype

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType


# Attach / Image hold a stored file (a site-relative URL) or a link to a file
# elsewhere, kept as is without downloading it. Nothing else - a stored
# ``javascript:`` value would become a clickable link in the form.
_FILE_URL_TYPES = frozenset({"Attach", "Image"})
_FILE_URL = re.compile(r"^(?:/(?!/)|https?://[^\s/]+)", re.IGNORECASE)


def _label(field: Any) -> dict[str, str]:
    """``{"label": <translated field label>}`` for message interpolation."""
    return {"label": _(field.label or field.fieldname)}


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
                errors.append(
                    f"{field.fieldname}: " + _("Field “%(label)s” is required") % _label(field)
                )

        if (
            field.fieldtype in _FILE_URL_TYPES
            and isinstance(value, str)
            and value
            and not _FILE_URL.match(value)
        ):
            errors.append(
                f"{field.fieldname}: "
                + _("Field “%(label)s” must be a file or an http(s) link") % _label(field)
            )

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
                # SQLite doesn't enforce VARCHAR length - check it ourselves so a
                # value that "fits" in dev doesn't fail only once deployed on
                # Postgres/MySQL, where VARCHAR(n) is a hard limit.
                if sa_type_name == "String" and args and len(str(value)) > args[0]:
                    errors.append(
                        f"{field.fieldname}: "
                        + _("Field “%(label)s” is too long (maximum %(max)s characters)")
                        % {**_label(field), "max": args[0]}
                    )

        if (field.min_value is not None or field.max_value is not None) and (
            value is not None and value != ""
        ):
            number = field.coerce(value)
            if isinstance(number, int | float) and not isinstance(number, bool):
                if field.min_value is not None and number < field.min_value:
                    errors.append(
                        f"{field.fieldname}: "
                        + _("Field “%(label)s” must be at least %(min)s")
                        % {**_label(field), "min": field.min_value}
                    )
                if field.max_value is not None and number > field.max_value:
                    errors.append(
                        f"{field.fieldname}: "
                        + _("Field “%(label)s” must be at most %(max)s")
                        % {**_label(field), "max": field.max_value}
                    )

        if field.regex and value is not None and value != "":
            try:
                matched = re.match(field.regex, str(value))
            except re.error:
                log.warning("field.invalid_regex", fieldname=field.fieldname, pattern=field.regex)
            else:
                if not matched:
                    errors.append(
                        f"{field.fieldname}: "
                        + _("Field “%(label)s” does not match the format") % _label(field)
                    )

    return errors
