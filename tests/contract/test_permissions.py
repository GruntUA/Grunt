"""Row-level permissions: which rows each user's list holds, the same on every
backend - and the same rows open one by one (``permission_checker.check`` with
a document): both are the one predicate, ``grunt.permissions.query``.

Every source of the read predicate (``grunt.permissions.query.read_predicate``):
role ``match`` (a field, ``!=``, a Link hop), several rules ORed, shares, role
scopes (narrowing their own role only), inherited access (``access_from``)
and child rows. NULL follows SQL: ``!=`` never matches it; ``link.field != value``
reads "not among the linked rows where ``field == value``" - a link to a row
whose field is empty is in, an empty link is not.

``None`` expected - no access to the DocType at all (403), not an empty list.
"""

import pytest

from tests.contract.permission_data import ALL
from tests.support import check_as, make_user


def _in_team(role: str, team: str) -> dict:
    """*role* held within *team* (a scoped role assignment)."""
    return {"role_name": role, "scope_doctype": "CpTeam", "scope_value": team}


def _role_ids(roles: list) -> str:
    return "+".join(
        r if isinstance(r, str) else f"{r['role_name']}@{r['scope_value']}" for r in roles
    )


# (user, roles) -> the tasks their list holds
TASK_CASES: list[tuple[str, list, set[str] | None]] = [
    ("alice@x.com", ["Reader"], ALL),
    ("alice@x.com", [], None),  # no read rule at all
    ("alice@x.com", ["Own"], {"K1", "K2"}),
    ("alice@x.com", ["Open"], {"K1", "K3"}),  # NULL status (K5) is not != 'Closed'
    ("alice@x.com", ["Lead"], {"K1"}),
    # teams not led by alice: T2 and T3 (no lead); K4 has no team at all
    ("alice@x.com", ["NotLead"], {"K2", "K3", "K5"}),
    ("alice@x.com", ["Own", "Open"], {"K1", "K2", "K3"}),  # rules OR together
    ("carol@x.com", ["Own"], {"K5", "K3"}),  # + the task shared with her
    ("carol@x.com", [], {"K3"}),  # a share alone grants its document
    # Reader within T2: tasks of T2 - a task with no team is outside the scope
    ("dave@x.com", [_in_team("Reader", "T2")], {"K2", "K3"}),
    # Own within T2: none of hers; a scope narrows its role, not her share (K1)
    ("erin@x.com", [_in_team("Own", "T2")], {"K1"}),
]


async def _names(
    ctx, db_session, engine, user, doctype: str, field: str = "name"
) -> set[str] | None:
    """The *field* values of *user*'s list of *doctype*; ``None`` - forbidden."""
    import grunt
    from grunt.errors import APIError

    async with grunt.context(db_session, engine, user):
        try:
            rows = await grunt.get_list(doctype, fields=[field], limit=100)
        except APIError as exc:
            assert exc.status_code == 403
            return None
        total = await grunt.count(doctype, respect_permissions=True)
    names = {r[field] for r in rows}
    assert total == len(names)
    return names


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    TASK_CASES,
    ids=[f"{u.split('@')[0]}-{_role_ids(r) or 'none'}" for u, r, _ in TASK_CASES],
)
async def test_task_list(ctx, permission_data, db_session, engine, case):
    email, roles, expected = case
    user = make_user(email, roles=roles)
    assert await _names(ctx, db_session, engine, user, "CpTask") == expected


@pytest.mark.asyncio
async def test_get_all_matches_the_list(ctx, permission_data, db_session, engine):
    import grunt
    from grunt.document.base import Document

    class CpTask(Document):
        doctype = "CpTask"

    for email, roles, expected in TASK_CASES:
        if expected is None:
            continue
        async with grunt.context(db_session, engine, make_user(email, roles=roles)):
            got = {d.name for d in await CpTask.get_list(limit=100)}
        assert got == expected, (email, roles)


# Notes follow the task they point at; a note pointing at nothing, the role's rule.
NOTE_CASES: list[tuple[str, list[str], set[str] | None]] = [
    ("alice@x.com", ["Lead"], {"N1", "N3"}),
    ("alice@x.com", ["Reader"], {"N1", "N2", "N3"}),
    ("carol@x.com", ["Own"], {"N2", "N3"}),  # K3 is shared with her
    ("alice@x.com", [], None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", NOTE_CASES, ids=[f"{u[:5]}-{'+'.join(r)}" for u, r, _ in NOTE_CASES]
)
async def test_inherited_access(ctx, permission_data, db_session, engine, case):
    email, roles, expected = case
    user = make_user(email, roles=roles)
    assert await _names(ctx, db_session, engine, user, "CpNote") == expected


@pytest.mark.asyncio
async def test_child_rows_follow_the_parent(ctx, permission_data, db_session, engine):
    alice = make_user("alice@x.com", roles=["Own"])
    labels = await _names(ctx, db_session, engine, alice, "CpStep", field="label")
    assert labels == {"K1-step", "K2-step"}


async def _opens(db_session, engine, user, doctype: str, rows: dict[str, dict]) -> set[str]:
    """The *rows* (name -> stored row) *user* may read one by one."""
    import grunt

    async with grunt.context(db_session, engine, user):
        meta = await grunt.get_meta(doctype)
        return {name for name, row in rows.items() if await check_as(user, meta, "read", row)}


async def _stored(db_session, engine, doctype: str, key: str = "name") -> dict[str, dict]:
    import grunt
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    async with grunt.context(db_session, engine, SYSTEM_USER):
        rows = await grunt.db.get_all(doctype, fields=["*"], limit=100)
    return {r[key]: r for r in rows}


@pytest.mark.asyncio
async def test_a_document_opens_exactly_when_the_list_holds_it(
    ctx, permission_data, db_session, engine
):
    """The single-document check and the list are one predicate: no rule can
    open a document its list hides, or hide one its list shows."""
    tasks = await _stored(db_session, engine, "CpTask")
    notes = await _stored(db_session, engine, "CpNote")
    steps = await _stored(db_session, engine, "CpStep", key="label")
    for email, roles, expected in TASK_CASES:
        user = make_user(email, roles=roles)
        assert await _opens(db_session, engine, user, "CpTask", tasks) == (expected or set()), (
            email,
            roles,
        )
        listed_notes = await _names(ctx, db_session, engine, user, "CpNote") or set()
        assert await _opens(db_session, engine, user, "CpNote", notes) == listed_notes, (
            email,
            roles,
        )
        listed_steps = await _names(ctx, db_session, engine, user, "CpStep", "label") or set()
        assert await _opens(db_session, engine, user, "CpStep", steps) == listed_steps, (
            email,
            roles,
        )


@pytest.mark.parametrize(
    "rule",
    [
        "assignee == user and status == 'Open'",
        "doc.status",
        "status == 5",
        "a.b.c == user",
        "owner == someone",
        "status == 'Open' and owner == 'x'",
        "status == 'a' or status == 'b'",
    ],
)
def test_unsupported_match_is_refused(rule):
    """A rule the predicate compiler can't translate is not saved - it would
    otherwise deny silently (or, as before, open documents lists hide)."""
    from pydantic import ValidationError

    from grunt.metadata.permission import DocPermission

    with pytest.raises(ValidationError):
        DocPermission(role="Own", actions=["read"], match=rule)
