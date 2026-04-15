from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Select", lambda f: ("String", 100), python_type="str | None")
