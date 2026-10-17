from datetime import time

from grunt.metadata.field import FieldType, register_field_type_class


class TimeField(FieldType):
    name = "Time"
    column_spec = ("Time",)
    empty_as_null = True
    python_type = "time | None"

    @classmethod
    def parse(cls, value):

        if isinstance(value, str):
            return time.fromisoformat(value)
        return value


def register():
    register_field_type_class(TimeField)
