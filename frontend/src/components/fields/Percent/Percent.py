from grunt.metadata.field import FieldType, parse_float, register_field_type_class


class PercentField(FieldType):
    name = "Percent"
    column_spec = ("Double",)
    empty_as_null = True
    python_type = "float | None"

    @classmethod
    def parse(cls, value):
        return parse_float(value)


def register():
    register_field_type_class(PercentField)
