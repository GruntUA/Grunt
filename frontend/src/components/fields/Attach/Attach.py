from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Attach", lambda f: ("String", 500), searchable=False, python_type="str | None")
