from grunt.metadata.field import FieldType, register_field_type_class


class IntField(FieldType):
    name = "Int"
    sa_factory = staticmethod(lambda f: ("Integer",))
    empty_as_null = True
    python_type = "int | None"

    @classmethod
    def coerce(cls, value):
        if value is None or value == "":
            return None
        if isinstance(value, str):
            try:
                return int(float(value))  # handles "1.0" → 1
            except ValueError:
                return None
        return value


def register():
    register_field_type_class(IntField)
