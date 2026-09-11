from grunt.metadata.field import FieldType, register_field_type_class


class ButtonField(FieldType):
    name = "Button"
    column_spec = None  # non-physical: UI action element only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(ButtonField)
