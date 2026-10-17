from __future__ import annotations

from grunt.metadata.field import FieldType, register_field_type_class


class DatetimeField(FieldType):
    name = "Datetime"
    column_spec = ("DateTime",)
    empty_as_null = True
    python_type = "datetime | None"

    @classmethod
    def parse(cls, value):
        from datetime import datetime

        if isinstance(value, str):
            return datetime.fromisoformat(value.replace(" ", "T"))
        return value


def register():
    register_field_type_class(DatetimeField)
