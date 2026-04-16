"""Tests for exporting schemas (migrated to whitelisted methods)."""

import pytest
# Direct API


@pytest.mark.asyncio
async def test_export_schemas_all(ctx):
    """Test that we can export all schemas directly."""
    from grunt.api.v1.meta import export_schemas
    data = await export_schemas()
    assert isinstance(data, dict)
    assert "User" in data
    assert "Role" in data
    assert "fields" in data["User"]


@pytest.mark.asyncio
async def test_export_schemas_filtered(ctx):
    """Test that we can filter schemas by name."""
    from grunt.api.v1.meta import export_schemas
    data = await export_schemas(names=["User", "Role"])
    assert len(data) == 2
    assert set(data.keys()) == {"User", "Role"}


@pytest.mark.asyncio
async def test_export_schemas_module(ctx):
    """Test that we can filter schemas by module."""
    from grunt.api.v1.meta import export_schemas
    # DocType "User" is in module "core"
    data = await export_schemas(module="core")
    assert "User" in data
    for dt in data.values():
        assert dt["module"] == "core"
