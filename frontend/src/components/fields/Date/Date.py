from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Date", lambda f: ("Date",), python_type="str | None")
