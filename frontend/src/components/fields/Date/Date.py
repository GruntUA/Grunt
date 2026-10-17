from __future__ import annotations

from grunt.metadata.field import FieldType, register_field_type_class


class DateField(FieldType):
    name = "Date"
    column_spec = ("Date",)
    empty_as_null = True
    python_type = "date | None"

    @classmethod
    def parse(cls, value):
        from datetime import date

        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        return value


def register():
    register_field_type_class(DateField)
