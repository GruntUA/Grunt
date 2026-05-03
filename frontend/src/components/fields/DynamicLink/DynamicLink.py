from grunt.metadata.field import register_field_type


def register():
    register_field_type("DynamicLink", lambda f: ("String", 255), python_type="str | None")
