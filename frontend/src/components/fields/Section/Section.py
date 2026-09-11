from grunt.metadata.field import FieldType, register_field_type_class


class SectionField(FieldType):
    name = "Section"
    column_spec = None  # non-physical: UI layout element only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(SectionField)
