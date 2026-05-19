from grunt.metadata.field import register_field_type


def register():
    register_field_type(
        "Rating", lambda f: ("Float", 2), empty_as_null=True, python_type="int | None"
    )
