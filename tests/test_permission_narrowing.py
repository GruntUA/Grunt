"""Speed-ups of the access predicate must not change what it allows: a list
filtered to one reference DocType works out access for that DocType only, and
"which DocTypes embed this child" is cached per registry state."""

import pytest

from grunt.permissions.query import pinned_values
from grunt.query.nodes import And, Cmp, In, Or
from tests.support import make_user
from tests.test_reference_permissions import cases  # noqa: F401 - fixture


def test_pinned_values():
    eq = Cmp("reference_doctype", "eq", "Task")
    assert pinned_values(eq, "reference_doctype") == {"Task"}
    both = And((In("reference_doctype", ("Task", "Note")), Cmp("x", "eq", 1)))
    assert pinned_values(both, "reference_doctype") == {"Task", "Note"}
    nested = And((And((eq,)), In("reference_doctype", ("Task", "Note"))))
    assert pinned_values(nested, "reference_doctype") == {"Task"}  # intersected
    assert pinned_values(Or((eq, Cmp("x", "eq", 1))), "reference_doctype") is None
    assert (
        pinned_values(In("reference_doctype", ("Task",), negate=True), "reference_doctype") is None
    )
    assert pinned_values(Cmp("reference_doctype", "ne", "Task"), "reference_doctype") is None
    assert pinned_values(None, "reference_doctype") is None


@pytest.mark.asyncio
async def test_narrowed_predicate_selects_the_same_rows(ctx, cases, db_session, engine):  # noqa: F811
    """For every user: the comments / files of SecretCase a pinned list holds are
    exactly those the full predicate allows."""
    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.query import read_predicate
    from grunt.query.query import Query
    from grunt.store.lookup import store_for

    pin = {"Comment": "reference_doctype", "File": "attached_to_doctype"}
    for who in (make_user("ann@example.com", roles=["Investigator"]), make_user("eve@x.com")):
        async with grunt.context(db_session, engine, who):
            for doctype, field in pin.items():
                meta = await doctype_registry.get_meta(doctype)
                where = Cmp(field, "eq", "SecretCase")
                store = store_for(meta)
                full = await read_predicate(who.email, meta)
                narrow = await read_predicate(who.email, meta, within=where)
                rows = []
                for predicate in (full, narrow):
                    query = Query(doctype=doctype, where=And((where, predicate)), fields=("name",))
                    rows.append(sorted(r["name"] for r in await store.fetch(query)))
                assert rows[0] == rows[1], (who.email, doctype)
            # Pinned to a DocType the column doesn't hold: nothing is worked out.
            comment = await doctype_registry.get_meta("Comment")
            elsewhere = Cmp("reference_doctype", "eq", "ToDo")
            narrowed = await read_predicate(who.email, comment, within=elsewhere)
            assert "SecretCase" not in repr(narrowed)


@pytest.mark.asyncio
async def test_child_parents_follow_registry_changes(ctx):
    from grunt.api.v1.meta import save_doctype
    from grunt.permissions.query import parent_doctypes

    assert "User" in [m.name for m in await parent_doctypes("UserRole")]
    assert [m.name for m in await parent_doctypes("NarrowRow")] == []
    await save_doctype(
        doctype_data={
            "name": "NarrowRow",
            "label": "Narrow Row",
            "module": "core",
            "is_child": True,
            "fields": [{"fieldname": "v", "label": "V", "fieldtype": "Data"}],
            "__is_new": True,
        }
    )
    await save_doctype(
        doctype_data={
            "name": "NarrowHolder",
            "label": "Narrow Holder",
            "module": "core",
            "fields": [
                {"fieldname": "rows", "label": "Rows", "fieldtype": "Table", "options": "NarrowRow"}
            ],
            "permissions": [{"role": "System Manager", "actions": ["read"]}],
            "__is_new": True,
        }
    )
    assert [m.name for m in await parent_doctypes("NarrowRow")] == ["NarrowHolder"]


def _linked_doctypes(expr) -> set[str]:
    """DocTypes the predicate asks in a subquery (``Linked`` nodes)."""
    from grunt.query.nodes import And, Linked, Or

    if isinstance(expr, Linked):
        return {expr.doctype} | _linked_doctypes(expr.where)
    if isinstance(expr, (And, Or)):
        return set().union(*(_linked_doctypes(e) for e in expr.items))
    return set()


@pytest.mark.asyncio
async def test_comments_of_a_table_less_doctype(ctx, db_session, engine):
    """Regression: the timeline of System Health (virtual, no table) asked for
    its comments with a subquery into a table that doesn't exist - a 500 on a
    site (the test database happens to have the table, so the predicate is
    checked directly)."""
    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.query import read_predicate

    comment = await doctype_registry.get_meta("Comment")
    pinned = And(
        (
            Cmp("reference_doctype", "eq", "SystemHealthReport"),
            Cmp("reference_id", "eq", "SystemHealthReport"),
        )
    )
    admin = make_user("admin@x.com", is_superadmin=True)
    async with grunt.context(db_session, engine, admin):
        predicate = await read_predicate("admin@x.com", comment, within=pinned)
        assert "SystemHealthReport" not in _linked_doctypes(predicate)
        rows = await grunt.get_list(
            "Comment",
            filters={
                "reference_doctype": "SystemHealthReport",
                "reference_id": "SystemHealthReport",
            },
        )
    assert rows == []
