from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Geolocation", lambda f: ("JSON",), searchable=False, python_type="str | None")
