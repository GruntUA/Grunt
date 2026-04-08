from grunt.core.metadata.field import register_field_type

def register():
    register_field_type("BarCode", lambda f: ("String", 255))
