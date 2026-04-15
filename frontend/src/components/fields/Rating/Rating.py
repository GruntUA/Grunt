from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Rating", lambda f: ("Float", 2), python_type="int | None")
