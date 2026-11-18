"""A document name may hold any character - `/` included: the REST routes take
the id as a path (``{doc_id:path}``), the client encodes it."""

from urllib.parse import quote

import pytest

NAME = "Ops/Night ?#%"


@pytest.mark.asyncio
async def test_crud_on_a_name_with_slash(client, auth_headers):
    r = await client.post("/api/v1/docs/Role", json={"role_name": NAME}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    assert r.json()["data"]["name"] == NAME

    url = f"/api/v1/docs/Role/{quote(NAME, safe='')}"
    r = await client.get(url, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["name"] == NAME

    r = await client.put(url, json={"desk_access": 0}, headers=auth_headers)
    assert r.status_code == 200, r.text

    r = await client.delete(url, headers=auth_headers)
    assert r.status_code == 204, r.text
    r = await client.get(url, headers=auth_headers)
    assert r.status_code == 404
