from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Float", lambda f: ("Float", 6), python_type="float | None")
