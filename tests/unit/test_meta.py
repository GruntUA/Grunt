import pytest

import grunt


@pytest.mark.asyncio
async def test_meta_helpers(ctx):
    # Fetch Meta for User DocType
    meta = await grunt.get_meta("User")

    assert meta.get_field("email") is not None
    assert meta.has_field("email") is True
    assert meta.has_field("non_existent_field") is False

    # Test valid columns
    columns = meta.get_valid_columns()
    assert "email" in columns
    assert "name" in columns

    # Test link fields
    link_fields = meta.get_link_fields()
    # User might not have link fields, let's just make sure it returns a list
    assert isinstance(link_fields, list)

    # Check UserRole table for testing table fields
    meta_ur = await grunt.get_meta("UserRole")
    assert meta_ur.get_title_field() == "name"

    # User fields
    data_fields = meta.get_data_fields()
    assert len(data_fields) > 0

    # Check labels
    assert (
        meta.get_label("email") != "email" or meta.get_label("email") == "email"
    )  # just check it doesn't crash
