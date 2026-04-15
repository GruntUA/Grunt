from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Datetime", lambda f: ("DateTime",), python_type="str | None")
