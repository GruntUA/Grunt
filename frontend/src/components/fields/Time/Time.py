from grunt.metadata.field import register_field_type


def register():
    register_field_type("Time", lambda f: ("Time",), python_type="str | None")
