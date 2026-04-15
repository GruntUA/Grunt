from grunt.core.metadata.field import register_field_type


def register():
    # MultiLink is non-physical (no DB column); registers python_type only for code scaffold.
    register_field_type("MultiLink", None, searchable=False, python_type="list[str] | None")
