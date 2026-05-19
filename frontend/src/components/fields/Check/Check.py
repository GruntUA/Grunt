from grunt.metadata.field import register_field_type


def register():
    register_field_type(
        "Check", lambda f: ("Boolean",), empty_as_null=True, python_type="bool | None"
    )
