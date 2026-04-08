from grunt.core.metadata.field import register_field_type


def register():
    register_field_type("Color", lambda f: ("String", 20))
