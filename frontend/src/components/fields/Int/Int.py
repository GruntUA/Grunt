from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Int", lambda f: ("Integer",), python_type="int | None")
