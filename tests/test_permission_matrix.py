"""The "Permissions" view of the DocType list (``grunt.api.v1.permission_matrix``):
one role's rules across DocTypes, saved through the DocType documents."""

import pytest
from fastapi import HTTPException

from grunt.api.v1.permission_matrix import get_role_matrix, save_role_matrix
from grunt.errors import ApplicationError
from tests.support import make_user

BOOK = {
    "name": "MxBook",
    "label": "Mx Book",
    "module": "test",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
        {"role": "Clerk", "actions": ["read"]},
        {"role": "Clerk", "actions": ["read", "write"], "match": "owner == user"},
    ],
}
NOTE = {**BOOK, "name": "MxNote", "label": "Mx Note", "permissions": BOOK["permissions"][:1]}


@pytest.fixture
async def books(ctx):
    from grunt.api.v1.meta import save_doctype

    for dt in (BOOK, NOTE):
        await save_doctype(doctype_data={**dt, "__is_new": True})
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    await ctx.db._session().commit()


async def _rules(name: str) -> list[dict]:
    from grunt.metadata.registry import doctype_registry

    meta = await doctype_registry.get_meta(name)
    assert meta is not None
    return [p.model_dump(exclude_defaults=True) for p in meta.permissions]


@pytest.mark.asyncio
async def test_reads_one_roles_rules(books):
    book, note = await get_role_matrix("Clerk", ["MxBook", "MxNote"])
    assert [(r["index"], r["actions"], r["match"]) for r in book["rules"]] == [
        (1, ["read"], None),
        (2, ["read", "write"], "owner == user"),
    ]
    assert (note["doctype"], note["rules"]) == ("MxNote", [])


@pytest.mark.asyncio
async def test_saves_adds_and_removes_rules(books):
    result = await save_role_matrix(
        "Clerk",
        [
            {
                "doctype": "MxBook",
                "rules": [
                    {"index": 1, "match": None, "actions": []},  # removed
                    {"index": 2, "match": "owner == user", "actions": ["read"]},
                ],
            },
            {"doctype": "MxNote", "rules": [{"index": None, "actions": ["read", "export"]}]},
        ],
    )
    assert [r["doctype"] for r in result] == ["MxBook", "MxNote"]
    assert await _rules("MxBook") == [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
        {"role": "Clerk", "actions": ["read"], "match": "owner == user"},
    ]
    assert (await _rules("MxNote"))[1] == {"role": "Clerk", "actions": ["read", "export"]}


@pytest.mark.asyncio
async def test_a_rule_with_a_condition_stays_without_actions(books):
    await save_role_matrix(
        "Clerk",
        [{"doctype": "MxBook", "rules": [{"index": 2, "match": "owner == user", "actions": []}]}],
    )
    assert (await _rules("MxBook"))[2] == {"role": "Clerk", "match": "owner == user"}


@pytest.mark.asyncio
async def test_a_changed_doctype_is_refused(books):
    # Row 1 has no match - the client saw a different table.
    with pytest.raises(ApplicationError) as exc_info:
        await save_role_matrix(
            "Clerk",
            [
                {
                    "doctype": "MxBook",
                    "rules": [{"index": 1, "match": "owner == user", "actions": []}],
                }
            ],
        )
    assert exc_info.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_unknown_role_is_refused(books):
    with pytest.raises(ApplicationError) as exc_info:
        await get_role_matrix("Nobody", ["MxBook"])
    assert exc_info.value.code == "NOT_FOUND"
    assert (await get_role_matrix("All", ["MxBook"]))[0]["rules"] == []


@pytest.mark.asyncio
async def test_needs_access_to_doctypes(books, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, make_user("clerk@x.com", roles=["Clerk"])):
        with pytest.raises(HTTPException) as exc_info:
            await get_role_matrix("Clerk", ["MxBook"])
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_a_rule_changed_by_someone_else_is_refused(books):
    # The editor loaded ["read"]; meanwhile the rule became ["read", "write"].
    await save_role_matrix(
        "Clerk", [{"doctype": "MxBook", "rules": [{"index": 1, "actions": ["read", "write"]}]}]
    )
    stale = {"index": 1, "match": None, "original": ["read"], "actions": ["read", "export"]}
    with pytest.raises(ApplicationError) as exc_info:
        await save_role_matrix("Clerk", [{"doctype": "MxBook", "rules": [stale]}])
    assert exc_info.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_a_new_rule_where_the_role_has_one_is_refused(books):
    with pytest.raises(ApplicationError) as exc_info:
        await save_role_matrix(
            "Clerk", [{"doctype": "MxBook", "rules": [{"index": None, "actions": ["read"]}]}]
        )
    assert exc_info.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_too_many_doctypes_writes_nothing(books):
    from grunt.api.v1.permission_matrix import MAX_DOCTYPES

    changes = [{"doctype": "MxNote", "rules": [{"index": None, "actions": ["read"]}]}] * (
        MAX_DOCTYPES + 1
    )
    with pytest.raises(ApplicationError) as exc_info:
        await save_role_matrix("Clerk", changes)
    assert exc_info.value.code == "VALIDATION_ERROR"
    assert (await get_role_matrix("Clerk", ["MxNote"]))[0]["rules"] == []
