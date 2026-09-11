from grunt.metadata.field import FieldType, register_field_type_class


class DefaultField(FieldType):
    name = "Default"
    column_spec = None  # non-physical: display-only element
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(DefaultField)
