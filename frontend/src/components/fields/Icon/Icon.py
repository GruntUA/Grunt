from grunt.metadata.field import FieldType, register_field_type_class


class IconField(FieldType):
    name = "Icon"
    column_spec = ("String",)
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(IconField)
