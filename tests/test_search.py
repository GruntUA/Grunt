"""Tests for the global search endpoint — GET /api/v1/method/grunt.api.v1.search.global_search."""

import pytest
from httpx2 import AsyncClient

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
    from grunt.auth.doctypes.User.user import User

    reg_user_data = {
        "email": "regular@example.com",
        "password": "pass123",
        "first_name": "Regular",
        "last_name": "User",
    }
    await ctx.new_doc("User", reg_user_data)
    await ctx.db._session().commit()
    return User(doctype="User", data={"email": "regular@example.com", "roles": []})


# ── Fixtures ──────────────────────────────────────────────────────────────

SIMPLE_DOCTYPE = {
    "name": "Документ",
    "label": "Документ",
    "module": "test",
    "fields": [
        {"fieldname": "title", "label": "Назва", "fieldtype": "Data", "in_list_view": True},
        {"fieldname": "content", "label": "Зміст", "fieldtype": "LongText"},
    ],
    "title_field": "title",
    "search_fields": ["title"],
    "autoname": "prompt",
    "permissions": [{"role": "All", "read": True, "write": True, "create": True, "delete": True}],
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
    from grunt.api.v1.search import global_search
    from grunt.errors import ApplicationError

    with pytest.raises(ApplicationError):
        await global_search(q="")


@pytest.mark.asyncio
async def test_search_q_empty_string_rejected(ctx):
    """global_search with empty q → ApplicationError."""
    from grunt.api.v1.search import global_search
    from grunt.errors import ApplicationError

    with pytest.raises(ApplicationError):
        await global_search(q="")


@pytest.mark.asyncio
async def test_search_limit_above_max_rejected(ctx):
    """global_search limit > 50 → ApplicationError."""
    from grunt.api.v1.search import global_search
    from grunt.errors import ApplicationError

    with pytest.raises(ApplicationError):
        await global_search(q="x", limit=51)


@pytest.mark.asyncio
async def test_search_limit_zero_rejected(ctx):
    """global_search limit=0 → ApplicationError."""
    from grunt.api.v1.search import global_search
    from grunt.errors import ApplicationError

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
            {"fieldname": "title", "label": "Назва", "fieldtype": "Data"},
            {"fieldname": "code", "label": "Код", "fieldtype": "Data"},
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
            {"fieldname": "info", "label": "Info", "fieldtype": "Data"},
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
        "fields": [{"fieldname": "name_ua", "label": "Назва", "fieldtype": "Data"}],
        "search_fields": ["name_ua"],
    }
    doctype_b = {
        "name": "Договір",
        "label": "Договір",
        "module": "crm",
        "fields": [{"fieldname": "subject", "label": "Тема", "fieldtype": "Data"}],
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
            "fields": [{"fieldname": "title", "label": "T", "fieldtype": "Data"}],
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
        "fields": [{"fieldname": "item", "label": "Елемент", "fieldtype": "Data"}],
        "search_fields": ["item"],
    }
    await create_and_sync(ctx, child_dt)

    data = await global_search(q="щось")
    assert not any(r["doctype"] == "РядокТаблиці" for r in data)


# ── Permission filtering ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_open_doctype_accessible_to_regular_user(ctx):
    """DocType with an explicit "All" read permission is open — regular user can find docs."""
    import grunt
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, SIMPLE_DOCTYPE)
    await create_doc(ctx, "Документ", {"name": "ДОК-001", "title": "Відкритий документ"})

    user = await regular_user_ctx(ctx)
    async with grunt.context(ctx.db._session(), ctx.get_engine(), user):
        data = await global_search(q="Відкритий")
        assert any(r["doctype"] == "Документ" for r in data)


@pytest.mark.asyncio
async def test_search_restricted_doctype_hidden_from_regular_user(ctx):
    """DocType restricted by role is excluded from results for users without that role."""
    import grunt
    from grunt.api.v1.search import global_search

    restricted_dt = {
        "name": "СекретнийДок",
        "label": "Секретний",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Data"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(ctx, restricted_dt)
    await create_doc(ctx, "СекретнийДок", {"name": "СЕК-001", "title": "Секретний вміст XYZ123"})

    # Regular user without Manager role → should not see results
    user = await regular_user_ctx(ctx)
    async with grunt.context(ctx.db._session(), ctx.get_engine(), user):
        data = await global_search(q="Секретний вміст XYZ123")
        assert not any(r["doctype"] == "СекретнийДок" for r in data)


@pytest.mark.asyncio
async def test_search_restricted_doctype_visible_to_system_manager(ctx):
    """System Manager sees results from all DocTypes regardless of permissions."""
    from grunt.api.v1.search import global_search

    restricted_dt = {
        "name": "АдмінДок",
        "label": "Адмін",
        "module": "test",
        "fields": [{"fieldname": "title", "label": "Назва", "fieldtype": "Data"}],
        "search_fields": ["title"],
        "permissions": [{"role": "Manager", "read": True}],
    }
    await create_and_sync(ctx, restricted_dt)
    await create_doc(ctx, "АдмінДок", {"name": "АД-001", "title": "Тільки для адміна ABC"})

    # Default ctx has System Manager
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
            "fields": [{"fieldname": "title", "fieldtype": "Data", "label": "T"}],
            "search_fields": ["title"],
        }
    )
    await ctx.db._session().commit()

    # Search should succeed even though БезТаблиці has no table
    data = await global_search(q="щось")
    # No error = success
    assert isinstance(data, list)


# ── Term semantics, ranking, FTS index consistency ────────────────────────

PERSON_DOCTYPE = {
    "name": "ПошукОсоба",
    "label": "Особа",
    "module": "test",
    "fields": [
        {"fieldname": "first_name", "label": "Імʼя", "fieldtype": "Data"},
        {"fieldname": "last_name", "label": "Прізвище", "fieldtype": "Data"},
        {"fieldname": "full_name", "label": "ПІБ", "fieldtype": "Data"},
        {"fieldname": "note", "label": "Примітка", "fieldtype": "LongText"},
    ],
    "title_field": "full_name",
    "search_fields": ["first_name", "last_name"],
    "autoname": "prompt",
    "permissions": [{"role": "All", "read": True, "write": True, "create": True, "delete": True}],
}


async def _people(ctx) -> None:
    await create_and_sync(ctx, PERSON_DOCTYPE)
    for name, first, last, note in [
        ("P-1", "Іван", "Петренко", ""),
        ("P-2", "Петро", "Іваненко", ""),
        ("P-3", "Олена", "Сидоренко", "згадка: Петренко"),
        ("P-4", "Марко", "Знижка_50%", ""),
    ]:
        await create_doc(
            ctx,
            "ПошукОсоба",
            {
                "name": name,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}",
                "note": note,
            },
        )


@pytest.mark.asyncio
async def test_global_search_all_terms_any_order_prefix(ctx):
    """Every term must match, in any order, as a word prefix, case-insensitively."""
    from grunt.api.v1.search import global_search

    await _people(ctx)
    names = {r["name"] for r in await global_search(q="петренко ІВАН")}
    assert names == {"P-1"}
    names = {r["name"] for r in await global_search(q="петр", doctype="ПошукОсоба")}
    assert {"P-1", "P-2", "P-3"} <= names


@pytest.mark.asyncio
async def test_global_search_ranks_title_hits_first(ctx):
    from grunt.api.v1.search import global_search

    await _people(ctx)
    results = await global_search(q="Петренко", doctype="ПошукОсоба")
    assert [r["name"] for r in results][:2] == ["P-1", "P-3"]


@pytest.mark.asyncio
async def test_global_search_index_follows_update_and_delete(ctx):
    from grunt.api.v1.search import global_search

    await _people(ctx)
    await ctx.save_doc("ПошукОсоба", "P-2", {"full_name": "Петро Коваль", "last_name": "Коваль"})
    await ctx.db._session().commit()

    assert not await global_search(q="Іваненко", doctype="ПошукОсоба")
    assert [r["name"] for r in await global_search(q="Коваль")] == ["P-2"]

    await ctx.delete_doc("ПошукОсоба", "P-2")
    await ctx.db._session().commit()
    assert not await global_search(q="Коваль")


@pytest.mark.asyncio
async def test_fts_table_rebuilt_when_out_of_sync(ctx):
    """ensure_table() refills the FTS5 table if it drifted from the index."""
    from sqlalchemy import text

    from grunt.api.v1.search import global_search
    from grunt.search.service import search_index_service

    await _people(ctx)
    session = ctx.db._session()
    if session.bind.dialect.name != "sqlite":
        pytest.skip("FTS5 companion table is SQLite-only")
    await session.execute(text("DELETE FROM grunt_search_fts"))
    await session.commit()
    assert not await global_search(q="Сидоренко")

    await search_index_service.ensure_table(ctx.get_engine())
    assert [r["name"] for r in await global_search(q="Сидоренко")] == ["P-3"]


async def _pg_search_index(conn):
    """(indisvalid, definition) of the PostgreSQL search index, or None."""
    from sqlalchemy import text

    row = (
        await conn.execute(
            text(
                "SELECT i.indisvalid, pg_get_indexdef(i.indexrelid) FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = 'grunt_search_idx_ts2'"
            )
        )
    ).first()
    return tuple(row) if row else None


async def _leave_invalid_pg_search_index(ctx):
    """A failed CREATE INDEX CONCURRENTLY under the search index's name."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    await _people(ctx)
    if ctx.db._session().bind.dialect.name != "postgresql":
        pytest.skip("CREATE INDEX CONCURRENTLY is PostgreSQL-only")
    async with ctx.get_engine().connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("DROP INDEX IF EXISTS grunt_search_idx_ts2"))
        with pytest.raises(DBAPIError):  # doctype repeats - the unique build fails
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX CONCURRENTLY grunt_search_idx_ts2 "
                    "ON grunt_search_index (doctype)"
                )
            )
        assert (await _pg_search_index(conn))[0] is False


@pytest.mark.asyncio
async def test_pg_invalid_search_index_is_rebuilt(ctx):
    from grunt.api.v1.search import global_search
    from grunt.search.service import search_index_service

    await _leave_invalid_pg_search_index(ctx)
    await search_index_service.ensure_table(ctx.get_engine())

    async with ctx.get_engine().connect() as conn:
        valid, definition = await _pg_search_index(conn)
    assert valid is True and "to_tsvector" in definition
    assert [r["name"] for r in await global_search(q="Сидоренко")] == ["P-3"]


@pytest.mark.asyncio
async def test_pg_search_index_build_in_another_process_is_left_alone(ctx):
    from sqlalchemy import text

    from grunt.search.service import search_index_service

    await _leave_invalid_pg_search_index(ctx)
    key = "hashtext('grunt_search_idx_ts2')"
    async with ctx.get_engine().connect() as other:
        await other.execute(text(f"SELECT pg_advisory_lock({key})"))
        try:
            await search_index_service.ensure_table(ctx.get_engine())
            assert (await _pg_search_index(other))[0] is False  # not dropped under the builder
        finally:
            await other.execute(text(f"SELECT pg_advisory_unlock({key})"))
        await other.commit()


@pytest.mark.asyncio
async def test_list_search_terms_across_fields_and_title(ctx):
    """List search: terms split across fields, title_field searched, % literal."""
    await _people(ctx)

    rows = await ctx.get_list("ПошукОсоба", search="петренко іван", fields=["name"])
    assert [r["name"] for r in rows] == ["P-1"]

    # full_name is only the title_field, not in search_fields.
    rows = await ctx.get_list("ПошукОсоба", search="Олена Сидоренко", fields=["name"])
    assert [r["name"] for r in rows] == ["P-3"]

    rows = await ctx.get_list("ПошукОсоба", search="50%", fields=["name"])
    assert [r["name"] for r in rows] == ["P-4"]
    assert not await ctx.get_list("ПошукОсоба", search="5_%", fields=["name"])


# ── in_global_search flag, purge, row-level permissions ───────────────────


@pytest.mark.asyncio
async def test_in_global_search_false_is_not_indexed(ctx):
    from grunt.api.v1.search import global_search

    await create_and_sync(ctx, {**SIMPLE_DOCTYPE, "name": "Поза", "in_global_search": False})
    await create_doc(ctx, "Поза", {"name": "П-1", "title": "Невидимий довідник"})
    assert not await global_search(q="Невидимий")
    # List search is unaffected.
    assert await ctx.get_list("Поза", search="Невидимий")


@pytest.mark.asyncio
async def test_switching_off_purges_existing_entries(ctx):
    from grunt.api.v1.meta import get_doctype, save_doctype
    from grunt.api.v1.search import global_search
    from grunt.search.service import search_index_service

    await create_and_sync(ctx, {**SIMPLE_DOCTYPE, "name": "Вимикач"})
    await create_doc(ctx, "Вимикач", {"name": "В-1", "title": "Зникаючий запис"})
    assert await global_search(q="Зникаючий")

    current = await get_doctype(name="Вимикач")
    await save_doctype(doctype_data={**current, "in_global_search": False})
    await ctx.db._session().commit()
    assert not await global_search(q="Зникаючий")

    # purge_excluded (run by `grunt migrate`) also drops stale entries.
    from sqlalchemy import insert, select

    from grunt.search.service import _search_index_table

    await ctx.db._session().execute(
        insert(_search_index_table).values(
            idx_id="Вимикач:X", doctype="Вимикач", doc_id="X", content_raw="x"
        )
    )
    from grunt.metadata.registry import doctype_registry

    all_dts = await doctype_registry.list_all()
    assert await search_index_service.purge_excluded(ctx.db._session(), all_dts) >= 1
    left = await ctx.db._session().execute(
        select(_search_index_table.c.idx_id).where(_search_index_table.c.doctype == "Вимикач")
    )
    assert left.first() is None


@pytest.mark.asyncio
async def test_hiding_a_field_rebuilds_the_index(ctx):
    """A field hidden from a role leaves the shared index - entries built before
    are rebuilt when the DocType is saved (its index signature changed)."""
    from grunt.api.v1.meta import get_doctype, save_doctype
    from grunt.api.v1.search import global_search

    doctype = {
        **SIMPLE_DOCTYPE,
        "name": "Ховання",
        "fields": [
            *SIMPLE_DOCTYPE["fields"],
            {"fieldname": "secret", "label": "Секрет", "fieldtype": "Data"},
        ],
    }
    await create_and_sync(ctx, doctype)
    await create_doc(ctx, "Ховання", {"name": "Х-1", "title": "Відкритий", "secret": "Таємниця"})
    assert await global_search(q="Таємниця")

    current = await get_doctype(name="Ховання")
    rows = [*current["permissions"], {"role": "Clerk", "read": True, "hidden_fields": ["secret"]}]
    await save_doctype(doctype_data={**current, "permissions": rows})
    await ctx.db._session().commit()
    assert not await global_search(q="Таємниця")
    assert await global_search(q="Відкритий")


@pytest.mark.asyncio
async def test_migrate_rebuilds_entries_from_before_signatures(ctx):
    """Entries indexed before signatures were kept may hold a hidden value;
    ``refresh_stale`` (run by ``grunt migrate``) rebuilds them."""
    from sqlalchemy import delete, select, update

    from grunt.metadata.registry import doctype_registry
    from grunt.search.service import (
        _index_state_table,
        _search_index_table,
        search_index_service,
    )

    doctype = {
        **SIMPLE_DOCTYPE,
        "name": "Спадок",
        "fields": [
            *SIMPLE_DOCTYPE["fields"],
            {"fieldname": "secret", "label": "Секрет", "fieldtype": "Data"},
        ],
        "permissions": [
            *SIMPLE_DOCTYPE["permissions"],
            {"role": "Clerk", "read": True, "hidden_fields": ["secret"]},
        ],
    }
    await create_and_sync(ctx, doctype)
    await create_doc(ctx, "Спадок", {"name": "С-1", "title": "Відкритий", "secret": "Таємниця"})
    session = ctx.db._session()
    # As an older version left it: the hidden value in the entry, no signature.
    t = _search_index_table
    await session.execute(
        update(t).where(t.c.doctype == "Спадок").values(content_raw="Відкритий Таємниця")
    )
    await session.execute(
        delete(_index_state_table).where(_index_state_table.c.doctype == "Спадок")
    )

    all_dts = await doctype_registry.list_all()
    assert "Спадок" in await search_index_service.refresh_stale(session, all_dts)
    content = (
        await session.execute(select(t.c.content_raw).where(t.c.doctype == "Спадок"))
    ).scalar_one()
    assert "Таємниця" not in content
    # Nothing changed since: the next migrate leaves it alone.
    assert "Спадок" not in await search_index_service.refresh_stale(session, all_dts)


@pytest.mark.asyncio
async def test_global_search_respects_row_level_match(ctx, db_session, engine):
    """A match-scoped role sees only the rows it could open, not all titles."""
    import grunt
    from grunt.api.v1.search import global_search
    from tests.support import make_user

    await create_and_sync(
        ctx,
        {
            **SIMPLE_DOCTYPE,
            "name": "СвоїЗаписи",
            "permissions": [
                {"role": "System Manager", "read": True, "write": True, "create": True},
                {"role": "Author", "read": True, "create": True, "match": "owner == user"},
            ],
        },
    )
    bob = "bob@example.com"
    await ctx.new_doc("User", {"email": bob, "first_name": "B", "last_name": "Ob"})
    await create_doc(ctx, "СвоїЗаписи", {"name": "С-адмін", "title": "Конфіденційна нотатка"})
    async with grunt.context(db_session, engine, make_user(bob, roles=["Author"])):
        await grunt.new_doc("СвоїЗаписи", {"name": "С-боб", "title": "Конфіденційна чернетка"})
        await db_session.commit()
        names = {r["name"] for r in await global_search(q="Конфіденційна")}
    assert names == {"С-боб"}
