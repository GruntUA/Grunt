from __future__ import annotations

from grunt.metadata.field import FieldType, register_field_type_class


class TimeField(FieldType):
    name = "Time"
    sa_factory = staticmethod(lambda f: ("Time",))
    empty_as_null = True
    python_type = "time | None"

    @classmethod
    def coerce(cls, value):
        from datetime import time  # noqa: PLC0415

        if value is None or value == "":
            return None
        if isinstance(value, str):
            return time.fromisoformat(value)
        return value


def register():
    register_field_type_class(TimeField)
