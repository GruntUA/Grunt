from grunt.core.metadata.field import register_field_type

def register():
    register_field_type("Check", lambda f: ("Boolean",))
