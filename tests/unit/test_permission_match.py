"""Tests for grunt.permissions.match.PermissionMatch — the single parser/
evaluator shared by row-level query filtering (to_sql) and per-document
checks (evaluate), replacing what used to be two independent
implementations in permissions/query.py and permissions/rbac.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, MetaData, String, Table

from grunt.permissions.match import PermissionMatch

_META = MetaData()
_TABLE = Table(
    "perm_match_test_table",
    _META,
    Column("name", String, primary_key=True),
    Column("owner", String),
    Column("status", String),
)


def _user(email: str) -> SimpleNamespace:
    return SimpleNamespace(email=email, roles=[], is_superadmin=False)


class TestToSql:
    def test_owner_eq_user(self):
        m = PermissionMatch("owner == user")
        cond = m.to_sql(_TABLE, _user("alice@example.com"))
        assert cond is not None
        compiled = str(cond.compile(compile_kwargs={"literal_binds": True}))
        assert "alice@example.com" in compiled

    def test_status_eq_literal(self):
        m = PermissionMatch("status == 'Published'")
        cond = m.to_sql(_TABLE, _user("alice@example.com"))
        assert cond is not None
        compiled = str(cond.compile(compile_kwargs={"literal_binds": True}))
        assert "Published" in compiled

    def test_not_equal(self):
        m = PermissionMatch("status != 'Archived'")
        cond = m.to_sql(_TABLE, _user("alice@example.com"))
        assert cond is not None

    def test_unknown_field_is_none(self):
        m = PermissionMatch("nonexistent == user")
        assert m.to_sql(_TABLE, _user("alice@example.com")) is None

    def test_boolean_logic_is_unparseable(self):
        m = PermissionMatch("owner == user and status == 'Open'")
        assert m.to_sql(_TABLE, _user("alice@example.com")) is None

    def test_numeric_literal_is_unparseable(self):
        m = PermissionMatch("status == 5")
        assert m.to_sql(_TABLE, _user("alice@example.com")) is None


class TestEvaluate:
    def test_owner_eq_user_true(self):
        m = PermissionMatch("owner == user")
        assert m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    def test_owner_eq_user_false(self):
        m = PermissionMatch("owner == user")
        assert not m.evaluate({"owner": "bob@example.com"}, _user("alice@example.com"))

    def test_boolean_logic_supported(self):
        """evaluate() supports full simpleeval syntax, wider than to_sql()'s
        narrow "field == value" form — that's the whole point of having two
        evaluation modes instead of forcing one.
        """
        m = PermissionMatch("owner == user and doc.get('status') == 'Open'")
        doc = {"owner": "alice@example.com", "status": "Open"}
        assert m.evaluate(doc, _user("alice@example.com"))

    def test_eval_error_fails_closed(self):
        """A broken/unsupported expression must deny, not grant."""
        m = PermissionMatch("doc.this_field_does_not_exist")
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    @pytest.mark.parametrize("expr", ["", "   "])
    def test_empty_expression_denies(self, expr):
        m = PermissionMatch(expr)
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    def test_field_named_user_is_not_shadowed_by_current_user_token(self):
        """Regression: a field literally named `user` (the natural field
        name for "who this row belongs to" on DocTypes like PushSubscription/
        Notification) used to collide with the reserved `user` name meaning
        "current user's email" in evaluate()'s simpleeval namespace — the
        doc's own `user` field was never consulted, so "user == user" was
        always True regardless of the document's actual owner.
        """
        m = PermissionMatch("user == user")
        assert m.evaluate({"user": "alice@example.com"}, _user("alice@example.com"))
        assert not m.evaluate({"user": "bob@example.com"}, _user("alice@example.com"))

    def test_narrow_form_denies_when_field_missing_from_doc(self):
        m = PermissionMatch("status == 'Open'")
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))
