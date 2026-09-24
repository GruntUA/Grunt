from grunt.metadata.field import FieldType, register_field_type_class


class HTMLField(FieldType):
    """Static HTML block in the form (hint, instruction). Content lives in `options`."""

    name = "HTML"
    column_spec = None  # non-physical: display only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(HTMLField)
