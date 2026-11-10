"""``grunt.query.run`` reads without permissions only when told so at the call."""

import pytest
from sqlalchemy import column

from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.query import run
from grunt.query.evaluate import matches
from grunt.query.nodes import TRUE, Cmp, Raw, and_
from grunt.query.query import Query, Sort


@pytest.mark.parametrize("fn", [run.fetch, run.count, run.aggregate, run.page])
async def test_run_needs_an_explicit_ignore_permissions(fn):
    query = Query("User")
    with pytest.raises(TypeError):
        await fn(query)  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError, match="ignore_permissions=True"):
        await fn(query, ignore_permissions=False)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("fn", [run.fetch, run.count, run.aggregate, run.page])
async def test_run_takes_no_user(fn):
    with pytest.raises(TypeError):
        await fn(Query("User"), user=SYSTEM_USER.email, ignore_permissions=True)  # pyright: ignore[reportCallIssue]


def test_narrowed_ands_onto_where():
    query = Query("User", where=Cmp("enabled", "eq", 1), sort=Sort("name", descending=False))
    narrowed = query.narrowed(Cmp("owner", "eq", "a@b"))
    assert narrowed.where == and_(Cmp("enabled", "eq", 1), Cmp("owner", "eq", "a@b"))
    assert narrowed.sort == query.sort
    assert query.narrowed(TRUE) == query


def test_raw_is_sql_only():
    with pytest.raises(NotImplementedError):
        matches(Raw(column("x") == 1), {"x": 1})
