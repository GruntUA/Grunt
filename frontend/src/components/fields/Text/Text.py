from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Text", lambda f: ("String", f.max_length or 255))
