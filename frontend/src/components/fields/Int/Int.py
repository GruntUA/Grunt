from grunt.metadata.field import FieldType, parse_int, register_field_type_class


class IntField(FieldType):
    name = "Int"
    column_spec = ("Integer",)
    empty_as_null = True
    python_type = "int | None"

    @classmethod
    def parse(cls, value):
        return parse_int(value)


def register():
    register_field_type_class(IntField)
