from grunt.metadata.field import FieldType, register_field_type_class

_MIN_VARCHAR = 64
_MAX_VARCHAR = 1000


class PasswordField(FieldType):
    """Single-line secret input.

    Same storage as ``Data`` (a ``String`` column) — the difference is purely
    presentational: the frontend renders it masked with a reveal toggle, and
    the value is kept out of full-text search.
    """

    name = "Password"
    sa_factory = staticmethod(
        lambda f: ("String", max(_MIN_VARCHAR, min(f.max_length or 255, _MAX_VARCHAR)))
    )
    python_type = "str | None"
    searchable = False
    empty_as_null = True


def register():
    register_field_type_class(PasswordField)
