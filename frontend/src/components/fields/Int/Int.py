from grunt.metadata.field import register_field_type


def register():
    register_field_type("Int", lambda f: ("Integer",), empty_as_null=True, python_type="int | None")
