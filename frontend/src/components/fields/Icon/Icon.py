from grunt.metadata.field import register_field_type


def register():
    register_field_type("Icon", lambda f: ("String",), searchable=False, python_type="str | None")
