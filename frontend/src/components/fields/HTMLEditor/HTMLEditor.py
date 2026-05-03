from grunt.metadata.field import register_field_type


def register():
    register_field_type("HTMLEditor", lambda f: ("Text",), searchable=False, python_type="str | None")
