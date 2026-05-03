from grunt.metadata.field import register_field_type


def register() -> None:
    """Register ColumnMapping as a JSON-backed field type."""
    register_field_type(
        "ColumnMapping",
        factory=lambda field: ("JSON",),
        searchable=False,
        python_type="dict[str, str] | None",
    )
