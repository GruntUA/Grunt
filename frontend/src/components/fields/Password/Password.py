from grunt.metadata.field import FieldType, register_field_type_class, varchar_spec


class PasswordField(FieldType):
    """Single-line secret input.

    Same storage as ``Data`` (a ``String`` column) - the difference is purely
    presentational: the frontend renders it masked with a reveal toggle, and
    the value is kept out of full-text search.
    """

    name = "Password"
    traits = frozenset({"sensitive"})
    column_spec = staticmethod(varchar_spec)
    python_type = "str | None"
    searchable = False
    empty_as_null = True


def register():
    register_field_type_class(PasswordField)
