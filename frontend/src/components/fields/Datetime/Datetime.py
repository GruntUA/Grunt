from __future__ import annotations

from grunt.metadata.field import FieldType, register_field_type_class


class DatetimeField(FieldType):
    name = "Datetime"
    sa_factory = staticmethod(lambda f: ("DateTime",))
    empty_as_null = True
    python_type = "str | None"

    @classmethod
    def coerce(cls, value):
        from datetime import datetime  # noqa: PLC0415
        if value is None or value == "":
            return None
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace(" ", "T"))
        return value


def register():
    register_field_type_class(DatetimeField)
