from grunt.metadata.field import FieldType, register_field_type_class, varchar_spec


class RowConditionField(FieldType):
    """A permission rule's row condition (``DocPermission.match``):
    ``<field>|<link>.<field> (==|!=) (user|'value')`` - stored as text, edited
    with a field / operator / value picker (PERMISSIONS_PLAN step 6f)."""

    name = "RowCondition"
    column_spec = staticmethod(varchar_spec)
    python_type = "str | None"
    searchable = False


def register():
    register_field_type_class(RowConditionField)
