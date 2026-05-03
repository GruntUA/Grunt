from grunt.metadata.field import register_field_type


def register():
    register_field_type("Color", lambda f: ("String", 20), python_type="str | None")
