from grunt.metadata.field import FieldType, register_field_type_class


class CheckField(FieldType):
    name = "Check"
    column_spec = staticmethod(lambda f: ("Boolean",))
    empty_as_null = True
    python_type = "bool | None"

    @classmethod
    def coerce(cls, value):
        if value is None or value == "":
            return False
        return bool(value)


def register():
    register_field_type_class(CheckField)
