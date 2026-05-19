from __future__ import annotations

from grunt.metadata.field import FieldType, register_field_type_class


class DateField(FieldType):
    name = "Date"
    sa_factory = staticmethod(lambda f: ("Date",))
    empty_as_null = True
    python_type = "date | None"

    @classmethod
    def coerce(cls, value):
        from datetime import date  # noqa: PLC0415

        if value is None or value == "":
            return None
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        return value


def register():
    register_field_type_class(DateField)
