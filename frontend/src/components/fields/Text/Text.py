from grunt.metadata.field import register_field_type

_MIN_VARCHAR = 64
_MAX_VARCHAR = 1000


def register():
    register_field_type(
        "Text",
        lambda f: ("String", max(_MIN_VARCHAR, min(f.max_length or 255, _MAX_VARCHAR))),
        python_type="str | None",
    )
