from grunt.metadata.field import FieldType, register_field_type_class


class SelectField(FieldType):
    name = "Select"
    traits = frozenset({"options"})
    column_spec = ("String", 100)
    python_type = "str | None"


def register():
    register_field_type_class(SelectField)
