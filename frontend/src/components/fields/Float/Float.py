from grunt.metadata.field import register_field_type


def register():
    register_field_type(
        "Float", lambda f: ("Float", 6), empty_as_null=True, python_type="float | None"
    )
