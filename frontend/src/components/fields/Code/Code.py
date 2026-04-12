from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Code", lambda f: ("Text",), searchable=False)
