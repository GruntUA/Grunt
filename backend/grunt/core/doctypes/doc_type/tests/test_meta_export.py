"""Tests for exporting schemas (migrated to whitelisted methods)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_export_schemas_all(client: AsyncClient, auth_headers: dict[str, str]):
    """Test that we can export all schemas via whitelisted method."""
    response = await client.get(
        "/api/v1/method/grunt.api.v1.meta.export_schemas", 
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, dict)
    assert "User" in data
    assert "Role" in data
    assert "fields" in data["User"]


@pytest.mark.asyncio
async def test_export_schemas_filtered(client: AsyncClient, auth_headers: dict[str, str]):
    """Test that we can filter schemas by name."""
    import json
    names_str = json.dumps(["User", "Role"])
    response = await client.get(
        f"/api/v1/method/grunt.api.v1.meta.export_schemas?names={names_str}", 
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    assert set(data.keys()) == {"User", "Role"}


@pytest.mark.asyncio
async def test_export_schemas_module(client: AsyncClient, auth_headers: dict[str, str]):
    """Test that we can filter schemas by module."""
    # DocType "User" is in module "core"
    response = await client.get(
        "/api/v1/method/grunt.api.v1.meta.export_schemas", 
        params={"module": "core"},
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "User" in data
    for dt in data.values():
        assert dt["module"] == "core"
