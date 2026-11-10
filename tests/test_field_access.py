"""A field hidden from a user (``DocPermission.hidden_fields``) is closed from
every side: it isn't read, written, filtered, sorted, grouped, searched or
probed through ``get_value`` / ``exists`` / year filters / the global index.

Roles: ``Clerk`` reads every row but not ``salary``; ``Own`` reads and writes
its own rows, ``salary`` hidden too; ``Payroll`` sees everything.
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException

from tests.support import make_user

TEAM = {
    "name": "FaTeam",
    "label": "Fa Team",
    "module": "test",
    "autoname": "prompt",
    "search_fields": ["code"],
    "fields": [
        {"fieldname": "budget", "label": "Budget", "fieldtype": "Int"},
        {"fieldname": "code", "label": "Code", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "Clerk", "read": True, "hidden_fields": ["budget", "code"]},
        {"role": "Own", "read": True, "hidden_fields": ["budget"]},
        {"role": "Payroll", "read": True},
    ],
}

PERSON = {
    "name": "FaPerson",
    "label": "Fa Person",
    "module": "test",
    "autoname": "prompt",
    "search_fields": ["note", "team"],
    "fields": [
        {"fieldname": "full_name", "label": "Full name", "fieldtype": "Data"},
        {"fieldname": "note", "label": "Note", "fieldtype": "Data", "in_global_search": True},
        {"fieldname": "salary", "label": "Salary", "fieldtype": "Int", "default": "0"},
        {"fieldname": "hired_on", "label": "Hired on", "fieldtype": "Date"},
        {"fieldname": "team", "label": "Team", "fieldtype": "Link", "options": "FaTeam"},
    ],
    "permissions": [
        {"role": "Clerk", "read": True, "hidden_fields": ["salary", "note", "hired_on"]},
        {
            "role": "Own",
            "read": True,
            "write": True,
            "create": True,
            "match": "owner == user",
            "hidden_fields": ["salary"],
        },
        {"role": "Payroll", "read": True, "write": True, "create": True},
    ],
}

CLERK = make_user("clerk@x.com", roles=["Clerk"])
OWN = make_user("own@x.com", roles=["Own"])
PAYROLL = make_user("payroll@x.com", roles=["Payroll"])


@pytest_asyncio.fixture
async def people(ctx):
    """Two people (P1 owned by ``own@x.com``) in team T1."""
    from grunt.api.v1.meta import save_doctype, sync_doctype

    for dt in (TEAM, PERSON):
        await save_doctype(doctype_data={**dt, "__is_new": True})
        await sync_doctype(name=dt["name"])
    await ctx.new_doc("FaTeam", {"name": "T1", "budget": 1000, "code": "team-code"})
    await ctx.new_doc(
        "FaPerson",
        {
            "name": "P1",
            "full_name": "Ivan",
            "note": "secret-word",
            "salary": 5000,
            "hired_on": "2021-03-01",
            "team": "T1",
        },
    )
    await ctx.new_doc("FaPerson", {"name": "P2", "full_name": "Olena", "salary": 7000})
    await ctx.db.set_value("FaPerson", "P1", "owner", "own@x.com")  # new_doc sets the owner
    await ctx.db._session().commit()


async def _as(ctx, db_session, engine, user, coro_fn):
    """Run *coro_fn* as *user*."""
    async with ctx.context(db_session, engine, user):
        return await coro_fn()


async def _forbidden(ctx, db_session, engine, user, coro_fn) -> bool:
    """Whether *coro_fn* run as *user* is refused with 403."""
    try:
        await _as(ctx, db_session, engine, user, coro_fn)
    except HTTPException as exc:  # APIError is one too
        return exc.status_code == 403
    return False


# ── reading ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rows_come_back_without_hidden_fields(ctx, people, db_session, engine):
    rows = await _as(
        ctx,
        db_session,
        engine,
        CLERK,
        lambda: ctx.get_list("FaPerson", fields=["name", "salary", "note"], limit=10),
    )
    assert rows and all("salary" not in r and "note" not in r for r in rows)
    rows = await _as(
        ctx,
        db_session,
        engine,
        PAYROLL,
        lambda: ctx.get_list("FaPerson", fields=["name", "salary", "note"], limit=10),
    )
    assert {r["salary"] for r in rows} == {5000, 7000}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"filters": {"salary__gt": 6000}},
        {"filters": {"salary": 5000}},
        {"order_by": "salary"},
    ],
    ids=["filter-op", "filter-eq", "sort"],
)
@pytest.mark.asyncio
async def test_a_hidden_field_cannot_be_queried_by(ctx, people, db_session, engine, kwargs):
    """Filtering or sorting by a field reveals its values row by row."""
    assert await _forbidden(
        ctx, db_session, engine, CLERK, lambda: ctx.get_list("FaPerson", limit=10, **kwargs)
    )
    if "filters" in kwargs:  # counting by it tells the same
        assert await _forbidden(
            ctx,
            db_session,
            engine,
            CLERK,
            lambda: ctx.count("FaPerson", filters=kwargs["filters"], respect_permissions=True),
        )
    # The same query is fine for whoever sees the field.
    await _as(ctx, db_session, engine, PAYROLL, lambda: ctx.get_list("FaPerson", **kwargs))


@pytest.mark.asyncio
async def test_a_link_hop_follows_the_target_rules(ctx, people, db_session, engine):
    """A query through a Link (``team`` -> ``FaTeam.budget``) is checked against
    the target DocType's hidden fields."""
    from grunt.query import run
    from grunt.query.nodes import Cmp, Linked
    from grunt.query.query import Query

    query = Query("FaPerson", where=Linked("team", "FaTeam", Cmp("budget", "gt", 500)))
    assert await _forbidden(
        ctx, db_session, engine, CLERK, lambda: run.fetch(query, user=CLERK.email)
    )
    rows = await _as(ctx, db_session, engine, PAYROLL, lambda: run.fetch(query, user=PAYROLL.email))
    assert [r["name"] for r in rows] == ["P1"]


@pytest.mark.asyncio
async def test_aggregates_refuse_hidden_fields(ctx, people, db_session, engine):
    assert await _forbidden(
        ctx,
        db_session,
        engine,
        CLERK,
        lambda: ctx.aggregate("FaPerson", aggregations={"total": "sum(salary)"}),
    )


@pytest.mark.asyncio
async def test_the_search_box_does_not_look_in_hidden_fields(ctx, people, db_session, engine):
    async def search():
        return await ctx.get_list("FaPerson", search="secret-word", limit=10)

    assert await _as(ctx, db_session, engine, CLERK, search) == []
    assert [r["name"] for r in await _as(ctx, db_session, engine, PAYROLL, search)] == ["P1"]


@pytest.mark.asyncio
async def test_the_search_box_does_not_look_through_a_link_into_hidden_fields(
    ctx, people, db_session, engine
):
    """A Link field is searched by its target's title / search fields - not by
    one the target's rules hide (``FaTeam.code`` from the clerk)."""

    async def search():
        return await ctx.get_list("FaPerson", search="team-code", limit=10)

    assert await _as(ctx, db_session, engine, CLERK, search) == []
    assert [r["name"] for r in await _as(ctx, db_session, engine, PAYROLL, search)] == ["P1"]


@pytest.mark.asyncio
async def test_get_value(ctx, people, db_session, engine):
    async def salary():
        return await ctx.get_value("FaPerson", "P1", "salary")

    async def name_of_p2():
        return await ctx.get_value("FaPerson", "P2", "full_name")

    async def whole_row():
        return await ctx.get_value("FaPerson", "P1", "*")

    assert await _forbidden(ctx, db_session, engine, CLERK, salary)
    assert await _as(ctx, db_session, engine, PAYROLL, salary) == 5000
    # A row the user's rule doesn't cover - the document-level check, not
    # just "may read the DocType".
    assert await _forbidden(ctx, db_session, engine, OWN, name_of_p2)
    assert "salary" not in await _as(ctx, db_session, engine, CLERK, whole_row)


@pytest.mark.asyncio
async def test_exists_follows_row_rules_and_hidden_fields(ctx, people, db_session, engine):
    async def p2_exists():
        return await ctx.exists("FaPerson", {"full_name": "Olena"})

    async def rich_exists():
        return await ctx.exists("FaPerson", {"salary__gt": 6000})

    assert await _as(ctx, db_session, engine, OWN, p2_exists) is None  # not their row
    assert await _as(ctx, db_session, engine, PAYROLL, p2_exists) == "P2"
    assert await _forbidden(ctx, db_session, engine, CLERK, rich_exists)


@pytest.mark.asyncio
async def test_year_filter_options_of_a_hidden_date(ctx, people, db_session, engine):
    from grunt.document.base import Document

    async def years():
        return await Document.get_field_years("FaPerson", "hired_on")

    assert await _as(ctx, db_session, engine, CLERK, years) == []
    assert await _as(ctx, db_session, engine, PAYROLL, years) == [2021]


# ── writing ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_hidden_field_cannot_be_written(ctx, people, db_session, engine):
    assert await _forbidden(
        ctx,
        db_session,
        engine,
        OWN,
        lambda: ctx.new_doc("FaPerson", {"name": "P3", "full_name": "X", "salary": 99999}),
    )
    assert await _forbidden(
        ctx, db_session, engine, OWN, lambda: ctx.save_doc("FaPerson", "P1", {"salary": 1})
    )
    assert await _forbidden(
        ctx, db_session, engine, OWN, lambda: ctx.set_value("FaPerson", "P1", "salary", 1)
    )


@pytest.mark.asyncio
async def test_unchanged_or_default_hidden_values_pass(ctx, people, db_session, engine):
    """A form may send a hidden field back as it was, or its default."""
    await _as(
        ctx,
        db_session,
        engine,
        OWN,
        lambda: ctx.new_doc("FaPerson", {"name": "P4", "full_name": "Y", "salary": "0"}),
    )
    await _as(
        ctx,
        db_session,
        engine,
        OWN,
        lambda: ctx.save_doc("FaPerson", "P1", {"full_name": "Ivan P.", "salary": 5000}),
    )


@pytest.mark.asyncio
async def test_set_value_checks_the_document(ctx, people, db_session, engine):
    """``owner == user`` grants writing *own* rows - not someone else's through
    the lightweight setter."""
    assert await _forbidden(
        ctx, db_session, engine, OWN, lambda: ctx.set_value("FaPerson", "P2", "full_name", "Z")
    )
    await _as(
        ctx, db_session, engine, OWN, lambda: ctx.set_value("FaPerson", "P1", "full_name", "Z")
    )


# ── global search ───────────────────────────────────────────────────────


def test_the_global_index_leaves_fields_hidden_from_some_role_out():
    from grunt.metadata.doctype import DocType
    from grunt.search.service import _build_content

    dt = DocType(**{k: v for k, v in PERSON.items() if k != "search_fields"})
    content = _build_content(dt, {"name": "P1", "full_name": "Ivan", "note": "secret-word"})
    assert "secret-word" not in content
