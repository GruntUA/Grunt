from grunt.metadata.field import FieldType, register_field_type_class


class ButtonField(FieldType):
    name = "Button"
    sa_factory = None  # non-physical: UI action element only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(ButtonField)
