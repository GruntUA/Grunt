from grunt.metadata.field import FieldType, register_field_type_class


class ImageField(FieldType):
    name = "Image"
    column_spec = staticmethod(lambda f: ("String", 500))
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(ImageField)
