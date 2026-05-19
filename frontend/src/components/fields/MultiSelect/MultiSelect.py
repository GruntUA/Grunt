from grunt.metadata.field import FieldType, register_field_type_class


class MultiSelectField(FieldType):
    name = "MultiSelect"
    sa_factory = staticmethod(lambda f: ("JSON",))
    searchable = False
    python_type = "list[str] | None"


def register():
    register_field_type_class(MultiSelectField)
