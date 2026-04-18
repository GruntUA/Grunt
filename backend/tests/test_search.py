"""Tests for the global search endpoint — GET /api/v1/method/grunt.api.v1.search.global_search."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

# Direct API

# ── Helpers ───────────────────────────────────────────────────────────────


async def create_and_sync(ctx, doctype: dict) -> None:
    """Create a DocType and sync it directly."""
    from grunt.api.v1.meta import save_doctype, sync_doctype

    await save_doctype(doctype_data=doctype)
    await sync_doctype(name=doctype["name"])
    await ctx.db._session().commit()


async def create_doc(ctx, doctype: str, data: dict) -> dict:
    """Create a document directly."""
    doc = await ctx.new_doc(doctype, data)
    await ctx.db._session().commit()
    return doc


async def regular_user_ctx(ctx):
    """Register a regular user and return the User object."""
    from grunt.core.doctypes.user.user import User

    reg_user_data = {
        "email": "regular@example.com",
        "password": "pass123",
        "full_name": "Regular User",
    }
    await ctx.new_doc("User", reg_user_data)
    await ctx.db._session().commit()
    return User(doctype="User", data={"email": "regular@example.com", "is_superadmin": False})


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
    """/method/global_search without token → 401."""
    resp = await client.get(
        "/api/v1/method/grunt.api.v1.search.global_search", params={"q": "test"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_invalid_token(client: AsyncClient):
    """/method/global_search with invalid token → 401."""
    resp = await client.get(
        "/api/v1/method/grunt.api.v1.search.global_search",
        params={"q": "test"},
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


# ── Input validation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_q_is_required(ctx):
    """global_search without q → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.search import global_search

    with pytest.raises(ApplicationError):
        await global_search(q="")


@pytest.mark.asyncio
async def test_search_q_empty_string_rejected(ctx):
    """global_search with empty q → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.search import global_search

    with pytest.raises(ApplicationError):
        await global_search(q="")


@pytest.mark.asyncio
async def test_search_limit_above_max_rejected(ctx):
    """global_search limit > 50 → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.search import global_search

    with pytest.raises(ApplicationError):
        await global_search(q="x", limit=51)


@pytest.mark.asyncio
async def test_search_limit_zero_rejected(ctx):
    """global_search limit=0 → ApplicationError."""
    from grunt.api.messages import ApplicationError
    from grunt.api.v1.search import global_search

    with pytest.raises(ApplicationError):
        await global_search(q="x", limit=0)


# ── Response structure ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_response_structure(ctx):
    """Response always has success=True (direct API returns data directly)."""
    from grunt.api.v1.search import global_search

    data = await global_search(q="нічого")
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_search_result_fields(ctx):
    """Each result contains doctype, id, name, display_title."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Тестовий документ"})

    results = await global_search(q="Тестовий")
    assert len(results) >= 1

    r = results[0]
    assert "doctype" in r
    assert "id" in r
    assert "name" in r
    assert "display_title" in r


# ── Basic search ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_no_results_for_unknown_query(ctx):
    """Query that matches nothing returns empty list."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    data = await global_search(q="zzz_не_існує_xyz")
    assert data == []


@pytest.mark.asyncio
async def test_search_finds_by_name_field(ctx):
    """Search matches the built-in `name` field."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "УН-2024-001", "title": "Щось"})

    data = await global_search(q="УН-2024")
    assert any(r["name"] == "УН-2024-001" for r in data)


@pytest.mark.asyncio
async def test_search_finds_by_title_field(ctx):
    """Search matches the title_field value."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Договір оренди"})

    data = await global_search(q="оренди")
    assert any(r["display_title"] == "Договір оренди" for r in data)


@pytest.mark.asyncio
async def test_search_finds_by_search_fields(ctx):
    """Search uses search_fields defined in DocType."""
    from grunt.api.v1.search import global_search

    doctype = {
        **SIMPLE_DOCTYPE,
        "fields": [
            {"fieldname": "title", "label": "Назва", "fieldtype": "Text"},
            {"fieldname": "code", "label": "Код", "fieldtype": "Text"},
        ],
        "search_fields": ["title", "code"],
    }
    await create_and_sync(ctx, doctype)
    await create_doc(
        ctx,
        "Документ",
        {"name": "ДОК-001", "title": "Назва", "code": "UNIQUE-CODE-XYZ"},
    )

    data = await global_search(q="UNIQUE-CODE-XYZ")
    assert len(data) >= 1
    assert data[0]["doctype"] == "Документ"


@pytest.mark.asyncio
async def test_search_partial_match(ctx):
    """Search works with partial substring (LIKE %q%)."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Акт приймання-передачі"})

    data = await global_search(q="прийм")
    assert any("прийм" in r["display_title"].lower() for r in data)


@pytest.mark.asyncio
async def test_display_title_uses_title_field(ctx):
    """display_title equals title_field value when it is set."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Людська назва"})

    data = await global_search(q="Людська")
    result = data[0]
    assert result["display_title"] == "Людська назва"
    assert result["name"] == "ДОК-001"


@pytest.mark.asyncio
async def test_display_title_falls_back_to_name(ctx):
    """display_title equals name when DocType has no title_field."""
    from grunt.api.v1.search import global_search

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
    await create_and_sync(ctx, doctype_no_title)
    await create_doc(ctx, "Запис", {"name": "ЗАП-001", "info": "дані"})

    data = await global_search(q="ЗАП-001")
    assert len(data) >= 1
    result = next(r for r in data if r["doctype"] == "Запис")
    assert result["display_title"] == "ЗАП-001"
    assert result["name"] == "ЗАП-001"


# ── Limit behaviour ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_default_limit_is_10(ctx):
    """Without limit param, at most 10 results returned."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    for i in range(15):
        await ctx.new_doc(
            "Документ",
            {"name": f"ДОК-{i:03}", "title": f"Документ номер {i}"},
        )
    await ctx.db._session().commit()

    data = await global_search(q="Документ")
    assert len(data) <= 10


@pytest.mark.asyncio
async def test_search_custom_limit_respected(ctx):
    """limit param caps total results."""
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    for i in range(10):
        await ctx.new_doc("Документ", {"name": f"ДОК-{i:03}", "title": f"Акт {i}"})
    await ctx.db._session().commit()

    data = await global_search(q="Акт", limit=3)
    assert len(data) <= 3


# ── Multi-DocType ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_across_multiple_doctypes(ctx):
    """Matching results from different DocTypes are returned together."""
    from grunt.api.v1.search import global_search

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
    await create_and_sync(ctx, doctype_a)
    await create_and_sync(ctx, doctype_b)

    await create_doc(ctx, "Клієнт", {"name": "КЛ-001", "name_ua": "Пошук ABC"})
    await create_doc(ctx, "Договір", {"name": "ДОГ-001", "subject": "Договір ABC"})

    data = await global_search(q="ABC")
    doctypes_found = {r["doctype"] for r in data}
    assert "Клієнт" in doctypes_found
    assert "Договір" in doctypes_found


@pytest.mark.asyncio
async def test_search_total_limit_across_doctypes(ctx):
    """Total results across all DocTypes respects limit."""
    from grunt.api.v1.search import global_search

    for dt_name, module in [("ТипА", "mod_a"), ("ТипБ", "mod_b")]:
        dt = {
            "name": dt_name,
            "label": dt_name,
            "module": module,
            "fields": [{"fieldname": "title", "label": "T", "fieldtype": "Text"}],
            "search_fields": ["title"],
        }
        await create_and_sync(ctx, dt)
        for i in range(5):
            await ctx.new_doc(
                dt_name,
                {"name": f"{dt_name}-{i}", "title": f"Пошук {dt_name} {i}"},
            )
    await ctx.db._session().commit()

    data = await global_search(q="Пошук", limit=4)
    assert len(data) <= 4


# ── Child DocType skipping ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_child_doctype_excluded_from_search(ctx):
    """DocTypes with is_child=True are never included in search results."""
    from grunt.api.v1.search import global_search

    child_dt = {
        "name": "РядокТаблиці",
        "label": "Рядок таблиці",
        "module": "test",
        "is_child": True,
        "fields": [{"fieldname": "item", "label": "Елемент", "fieldtype": "Text"}],
        "search_fields": ["item"],
    }
    await create_and_sync(ctx, child_dt)

    data = await global_search(q="щось")
    assert not any(r["doctype"] == "РядокТаблиці" for r in data)


# ── Permission filtering ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_open_doctype_accessible_to_regular_user(ctx):
    """DocType without permissions config is open — regular user can find docs."""
    from grunt.api.v1.search import global_search
    from grunt.app import grunt

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Відкритий документ"})

    user = await regular_user_ctx(ctx)
    async with grunt.context(ctx.db._session(), ctx._require_engine(), user):
        data = await global_search(q="Відкритий")
        assert any(r["doctype"] == "Документ" for r in data)


@pytest.mark.asyncio
async def test_search_restricted_doctype_hidden_from_regular_user(ctx):
    """DocType restricted by role is excluded from results for users without that role."""
    from grunt.api.v1.search import global_search
    from grunt.app import grunt

    restricted_dt = {
        "name": "СекретнийДок",
        "label": "Секретний",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Text"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(ctx, restricted_dt)
    await create_doc(ctx, "СекретнийДок", {"name": "СЕК-001", "title": "Секретний вміст XYZ123"})

    # Regular user without Manager role → should not see results
    user = await regular_user_ctx(ctx)
    async with grunt.context(ctx.db._session(), ctx._require_engine(), user):
        data = await global_search(q="Секретний вміст XYZ123")
        assert not any(r["doctype"] == "СекретнийДок" for r in data)


@pytest.mark.asyncio
async def test_search_restricted_doctype_visible_to_superadmin(ctx):
    """Superadmin sees results from all DocTypes regardless of permissions."""
    from grunt.api.v1.search import global_search

    restricted_dt = {
        "name": "АдмінДок",
        "label": "Адмін",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Text"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(ctx, restricted_dt)
    await create_doc(ctx, "АдмінДок", {"name": "АД-001", "title": "Тільки для адміна ABC"})

    # Default ctx has superadmin
    data = await global_search(q="Тільки для адміна ABC")
    assert any(r["doctype"] == "АдмінДок" for r in data)


# ── Error resilience ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_skips_doctype_without_table(ctx):
    """DocType registered but not synced (no table) → skipped, no 500 error."""
    from grunt.api.v1.meta import save_doctype
    from grunt.api.v1.search import global_search

    # Register DocType without calling sync_doctype
    await save_doctype(
        doctype_data={
            "name": "БезТаблиці",
            "label": "Без таблиці",
            "module": "test",
            "fields": [{"fieldname": "title", "fieldtype": "Text", "label": "T"}],
            "search_fields": ["title"],
        }
    )
    await ctx.db._session().commit()

    # Search should succeed even though БезТаблиці has no table
    data = await global_search(q="щось")
    # No error = success
    assert isinstance(data, list)
