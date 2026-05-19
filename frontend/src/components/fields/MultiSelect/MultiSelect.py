from grunt.metadata.field import register_field_type


def register():
    register_field_type(
        "MultiSelect", lambda f: ("JSON",), searchable=False, python_type="list[str] | None"
    )
