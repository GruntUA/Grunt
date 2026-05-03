from grunt.metadata.field import register_field_type


def register():
    register_field_type("Duration", lambda f: ("Float", 6), python_type="float | None")
