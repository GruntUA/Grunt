from grunt.metadata.field import register_field_type


def register():
    register_field_type("LongText", lambda f: ("Text",), python_type="str | None")
