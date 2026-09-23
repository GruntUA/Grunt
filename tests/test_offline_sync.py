"""Server side of offline sync: stale edits are refused (409) instead of
overwriting newer data, and a retried create with the same Idempotency-Key
does not create a second document."""

from __future__ import annotations

import pytest

DOCS = "/api/v1/docs/Role"


async def _role(client, auth_headers, name: str) -> dict:
    r = await client.post(DOCS, json={"role_name": name}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


@pytest.mark.asyncio
async def test_stale_offline_edit_is_a_conflict(client, auth_headers):
    role = await _role(client, auth_headers, "Offline Clerk")
    base = role["modified_at"]

    # Someone else saves first…
    r = await client.put(
        f"{DOCS}/{role['name']}", json={"description": "theirs"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text

    # …so the queued offline edit based on the old copy is refused.
    stale = await client.put(
        f"{DOCS}/{role['name']}",
        json={"description": "mine", "__base_modified_at": base},
        headers=auth_headers,
    )
    assert stale.status_code == 409

    fresh_base = r.json()["data"]["modified_at"]
    ok = await client.put(
        f"{DOCS}/{role['name']}",
        json={"description": "mine", "__base_modified_at": fresh_base},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["description"] == "mine"


@pytest.mark.asyncio
async def test_retried_create_with_same_key_is_not_duplicated(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "k-123"}
    first = await client.post(DOCS, json={"role_name": "Idem Role"}, headers=headers)
    again = await client.post(DOCS, json={"role_name": "Idem Role"}, headers=headers)
    assert first.status_code in (200, 201)
    assert again.status_code == first.status_code
    assert again.headers.get("idempotent-replay") == "true"
    assert again.json() == first.json()

    other = await client.post(
        DOCS, json={"role_name": "Idem Role"}, headers={**auth_headers, "Idempotency-Key": "k-456"}
    )
    assert other.status_code >= 400  # a genuinely new request still runs (duplicate name)
