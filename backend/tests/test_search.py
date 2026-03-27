"""Tests for the global search endpoint — GET /api/v1/search."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ── Helpers ───────────────────────────────────────────────────────────────


async def create_and_sync(client: AsyncClient, headers: dict, doctype: dict) -> None:
    """Create a DocType (sync_table is called internally by registry.register)."""
    resp = await client.post("/api/v1/meta/doctypes", json=doctype, headers=headers)
    assert resp.status_code == 201, resp.text


async def create_doc(
    client: AsyncClient, headers: dict, doctype: str, data: dict
) -> dict:
    resp = await client.post(f"/api/v1/docs/{doctype}", json=data, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def regular_user_headers(client: AsyncClient) -> dict[str, str]:
    """Register a regular (non-superadmin) user and return auth headers."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "regular@example.com", "password": "pass123", "full_name": "Regular User"},
    )
    resp = await client.post(
        "/api/v1/auth/token",
        data={"username": "regular@example.com", "password": "pass123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ──────────────────────────────────────────────────────────────

SIMPLE_DOCTYPE = {
    "name": "Документ",
    "label": "Документ",
    "module": "test",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Text", "in_list_view": True},
        {"fieldname": "content", "label": "Зміст", "fieldtype": "LongText"},
    ],
    "title_field": "title",
    "search_fields": ["title"],
    "autoname": "prompt",
}


# ── Authentication ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient):
    """GET /search without token → 401."""
    resp = await client.get("/api/v1/search", params={"q": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_invalid_token(client: AsyncClient):
    """GET /search with invalid token → 401."""
    resp = await client.get(
        "/api/v1/search",
        params={"q": "test"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


# ── Input validation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_q_is_required(client: AsyncClient, auth_headers: dict):
    """GET /search without q param → 422."""
    resp = await client.get("/api/v1/search", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_q_empty_string_rejected(client: AsyncClient, auth_headers: dict):
    """GET /search?q= (empty) → 422 (min_length=1)."""
    resp = await client.get("/api/v1/search", params={"q": ""}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_above_max_rejected(client: AsyncClient, auth_headers: dict):
    """GET /search?limit=51 → 422 (max 50)."""
    resp = await client.get(
        "/api/v1/search", params={"q": "x", "limit": 51}, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_zero_rejected(client: AsyncClient, auth_headers: dict):
    """GET /search?limit=0 → 422 (min 1)."""
    resp = await client.get(
        "/api/v1/search", params={"q": "x", "limit": 0}, headers=auth_headers
    )
    assert resp.status_code == 422


# ── Response structure ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_response_structure(client: AsyncClient, auth_headers: dict):
    """Response always has success=True and data array."""
    resp = await client.get(
        "/api/v1/search", params={"q": "нічого"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_search_result_fields(client: AsyncClient, auth_headers: dict):
    """Each result contains doctype, id, name, display_title."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Тестовий документ"})

    resp = await client.get(
        "/api/v1/search", params={"q": "Тестовий"}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert len(results) >= 1

    r = results[0]
    assert "doctype" in r
    assert "id" in r
    assert "name" in r
    assert "display_title" in r


# ── Basic search ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_no_results_for_unknown_query(client: AsyncClient, auth_headers: dict):
    """Query that matches nothing returns empty list."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    resp = await client.get(
        "/api/v1/search", params={"q": "zzz_не_існує_xyz"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_search_finds_by_name_field(client: AsyncClient, auth_headers: dict):
    """Search matches the built-in `name` field."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(client, auth_headers, "Документ", {"name": "УН-2024-001", "title": "Щось"})

    resp = await client.get(
        "/api/v1/search", params={"q": "УН-2024"}, headers=auth_headers
    )
    results = resp.json()["data"]
    assert any(r["name"] == "УН-2024-001" for r in results)


@pytest.mark.asyncio
async def test_search_finds_by_title_field(client: AsyncClient, auth_headers: dict):
    """Search matches the title_field value."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Договір оренди"})

    resp = await client.get(
        "/api/v1/search", params={"q": "оренди"}, headers=auth_headers
    )
    results = resp.json()["data"]
    assert any(r["display_title"] == "Договір оренди" for r in results)


@pytest.mark.asyncio
async def test_search_finds_by_search_fields(client: AsyncClient, auth_headers: dict):
    """Search uses search_fields defined in DocType."""
    doctype = {
        **SIMPLE_DOCTYPE,
        "fields": [
            {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
            {"fieldname": "code", "label": "Код", "fieldtype": "Text"},
        ],
        "search_fields": ["title", "code"],
    }
    await create_and_sync(client, auth_headers, doctype)
    await create_doc(
        client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Назва", "code": "UNIQUE-CODE-XYZ"}
    )

    resp = await client.get(
        "/api/v1/search", params={"q": "UNIQUE-CODE-XYZ"}, headers=auth_headers
    )
    results = resp.json()["data"]
    assert len(results) >= 1
    assert results[0]["doctype"] == "Документ"


@pytest.mark.asyncio
async def test_search_partial_match(client: AsyncClient, auth_headers: dict):
    """Search works with partial substring (LIKE %q%)."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Акт приймання-передачі"})

    resp = await client.get(
        "/api/v1/search", params={"q": "прийм"}, headers=auth_headers
    )
    results = resp.json()["data"]
    assert any("прийм" in r["display_title"].lower() for r in results)


@pytest.mark.asyncio
async def test_display_title_uses_title_field(client: AsyncClient, auth_headers: dict):
    """display_title equals title_field value when it is set."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(
        client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Людська назва"}
    )

    resp = await client.get(
        "/api/v1/search", params={"q": "Людська"}, headers=auth_headers
    )
    result = resp.json()["data"][0]
    assert result["display_title"] == "Людська назва"
    assert result["name"] == "ДОК-001"


@pytest.mark.asyncio
async def test_display_title_falls_back_to_name(client: AsyncClient, auth_headers: dict):
    """display_title equals name when DocType has no title_field."""
    doctype_no_title = {
        "name": "Запис",
        "label": "Запис",
        "module": "test",
        "autoname": "prompt",
        "fields": [
            {"fieldname": "info", "label": "Info", "fieldtype": "Text"},
        ],
        # no title_field, no search_fields
    }
    await create_and_sync(client, auth_headers, doctype_no_title)
    await create_doc(client, auth_headers, "Запис", {"name": "ЗАП-001", "info": "дані"})

    resp = await client.get(
        "/api/v1/search", params={"q": "ЗАП-001"}, headers=auth_headers
    )
    results = resp.json()["data"]
    assert len(results) >= 1
    result = next(r for r in results if r["doctype"] == "Запис")
    assert result["display_title"] == "ЗАП-001"
    assert result["name"] == "ЗАП-001"


# ── Limit behaviour ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_default_limit_is_10(client: AsyncClient, auth_headers: dict):
    """Without limit param, at most 10 results returned."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    for i in range(15):
        await create_doc(
            client, auth_headers, "Документ",
            {"name": f"ДОК-{i:03}", "title": f"Документ номер {i}"}
        )

    resp = await client.get(
        "/api/v1/search", params={"q": "Документ"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) <= 10


@pytest.mark.asyncio
async def test_search_custom_limit_respected(client: AsyncClient, auth_headers: dict):
    """limit param caps total results."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    for i in range(10):
        await create_doc(
            client, auth_headers, "Документ",
            {"name": f"ДОК-{i:03}", "title": f"Акт {i}"}
        )

    resp = await client.get(
        "/api/v1/search", params={"q": "Акт", "limit": 3}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) <= 3


# ── Multi-DocType ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_across_multiple_doctypes(client: AsyncClient, auth_headers: dict):
    """Matching results from different DocTypes are returned together."""
    doctype_a = {
        "name": "Клієнт",
        "label": "Клієнт",
        "module": "crm",
        "fields": [{"fieldname": "name_ua", "label": "Назва", "fieldtype": "Text"}],
        "search_fields": ["name_ua"],
    }
    doctype_b = {
        "name": "Договір",
        "label": "Договір",
        "module": "crm",
        "fields": [{"fieldname": "subject", "label": "Тема", "fieldtype": "Text"}],
        "search_fields": ["subject"],
        "title_field": "subject",
    }
    await create_and_sync(client, auth_headers, doctype_a)
    await create_and_sync(client, auth_headers, doctype_b)

    await create_doc(client, auth_headers, "Клієнт", {"name": "КЛ-001", "name_ua": "Пошук ABC"})
    await create_doc(client, auth_headers, "Договір", {"name": "ДОГ-001", "subject": "Договір ABC"})

    resp = await client.get(
        "/api/v1/search", params={"q": "ABC"}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    doctypes_found = {r["doctype"] for r in results}
    assert "Клієнт" in doctypes_found
    assert "Договір" in doctypes_found


@pytest.mark.asyncio
async def test_search_total_limit_across_doctypes(client: AsyncClient, auth_headers: dict):
    """Total results across all DocTypes respects limit."""
    for dt_name, module in [("ТипА", "mod_a"), ("ТипБ", "mod_b")]:
        dt = {
            "name": dt_name, "label": dt_name, "module": module,
            "fields": [{"fieldname": "title", "label": "T", "fieldtype": "Text"}],
            "search_fields": ["title"],
        }
        await create_and_sync(client, auth_headers, dt)
        for i in range(5):
            await create_doc(client, auth_headers, dt_name, {"name": f"{dt_name}-{i}", "title": f"Пошук {dt_name} {i}"})

    resp = await client.get(
        "/api/v1/search", params={"q": "Пошук", "limit": 4}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) <= 4


# ── Child DocType skipping ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_child_doctype_excluded_from_search(client: AsyncClient, auth_headers: dict):
    """DocTypes with is_child=True are never included in search results."""
    child_dt = {
        "name": "РядокТаблиці",
        "label": "Рядок таблиці",
        "module": "test",
        "is_child": True,
        "fields": [{"fieldname": "item", "label": "Елемент", "fieldtype": "Text"}],
        "search_fields": ["item"],
    }
    await create_and_sync(client, auth_headers, child_dt)
    # Child doctypes require parent_id so we skip document creation;
    # the search endpoint should skip the DocType entirely based on is_child flag.

    resp = await client.get(
        "/api/v1/search", params={"q": "щось"}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert not any(r["doctype"] == "РядокТаблиці" for r in results)


# ── Permission filtering ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_open_doctype_accessible_to_regular_user(
    client: AsyncClient, auth_headers: dict
):
    """DocType without permissions config is open — regular user can find docs."""
    await create_and_sync(client, auth_headers, SIMPLE_DOCTYPE)
    await create_doc(
        client, auth_headers, "Документ", {"name": "ДОК-001", "title": "Відкритий документ"}
    )

    user_headers = await regular_user_headers(client)
    resp = await client.get(
        "/api/v1/search", params={"q": "Відкритий"}, headers=user_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert any(r["doctype"] == "Документ" for r in results)


@pytest.mark.asyncio
async def test_search_restricted_doctype_hidden_from_regular_user(
    client: AsyncClient, auth_headers: dict
):
    """DocType restricted by role is excluded from results for users without that role."""
    restricted_dt = {
        "name": "СекретнийДок",
        "label": "Секретний",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Text"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(client, auth_headers, restricted_dt)
    await create_doc(
        client, auth_headers, "СекретнийДок",
        {"name": "СЕК-001", "title": "Секретний вміст XYZ123"}
    )

    # Regular user without Manager role → should not see results
    user_headers = await regular_user_headers(client)
    resp = await client.get(
        "/api/v1/search", params={"q": "Секретний вміст XYZ123"}, headers=user_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert not any(r["doctype"] == "СекретнийДок" for r in results)


@pytest.mark.asyncio
async def test_search_restricted_doctype_visible_to_superadmin(
    client: AsyncClient, auth_headers: dict
):
    """Superadmin sees results from all DocTypes regardless of permissions."""
    restricted_dt = {
        "name": "АдмінДок",
        "label": "Адмін",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Text"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(client, auth_headers, restricted_dt)
    await create_doc(
        client, auth_headers, "АдмінДок", {"name": "АД-001", "title": "Тільки для адміна ABC"}
    )

    resp = await client.get(
        "/api/v1/search", params={"q": "Тільки для адміна ABC"}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert any(r["doctype"] == "АдмінДок" for r in results)


# ── Error resilience ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_skips_doctype_without_table(client: AsyncClient, auth_headers: dict):
    """DocType registered but not synced (no table) → skipped, no 500 error."""
    # Register DocType without calling /sync (no table created)
    resp = await client.post(
        "/api/v1/meta/doctypes",
        json={
            "name": "БезТаблиці",
            "label": "Без таблиці",
            "module": "test",
            "fields": [{"fieldname": "title", "fieldtype": "Text", "label": "T"}],
            "search_fields": ["title"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Search should succeed even though БезТаблиці has no table
    resp = await client.get(
        "/api/v1/search", params={"q": "щось"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
