from grunt.metadata.field import FieldType, register_field_type_class


class TabField(FieldType):
    name = "Tab"
    sa_factory = None  # non-physical: UI layout element only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(TabField)
