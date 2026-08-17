"""Regression: DocLink, BackgroundTaskLog, ScheduledJobLog, SqlProfilerQuery
and SqlProfilerSpan used to have no `permissions` at all. All five are
written exclusively through raw SQLAlchemy or `grunt.system_context()` (never
under a regular user's own context), so restricting them costs nothing —
verified per-doctype before applying the fix (see project memory).

DocLink (source/target doc reference graph) and SqlProfilerQuery/Span (raw
SQL text, including literal bound values, and per-call timings) are read via
their own dedicated code paths outside `doctype.permissions` entirely,
mirroring SqlProfilerRequest's already-shipped `{"role": "System Manager",
"read": true}`-only shape — no doctype here needs write/create/delete for
anyone, including System Manager, since nothing legitimate ever calls
grunt.new_doc/save_doc/delete_doc on them.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.rbac import permission_checker

_GRUNT_ROOT = Path(__file__).resolve().parents[2] / "grunt"

_DOCTYPE_JSON = {
    "DocLink": _GRUNT_ROOT / "document/doctypes/DocLink/DocLink.json",
    "BackgroundTaskLog": _GRUNT_ROOT / "tasks/doctypes/BackgroundTaskLog/BackgroundTaskLog.json",
    "ScheduledJobLog": _GRUNT_ROOT / "tasks/doctypes/ScheduledJobLog/ScheduledJobLog.json",
    "SqlProfilerQuery": (
        _GRUNT_ROOT / "monitoring/doctypes/SqlProfilerQuery/SqlProfilerQuery.json"
    ),
    "SqlProfilerSpan": _GRUNT_ROOT / "monitoring/doctypes/SqlProfilerSpan/SqlProfilerSpan.json",
}


def _load(doctype_name: str) -> DocType:
    data = json.loads(_DOCTYPE_JSON[doctype_name].read_text(encoding="utf-8"))
    return DocType.model_validate(data)


def _plain_user() -> SimpleNamespace:
    return SimpleNamespace(email="plain@example.com", roles=[], is_superadmin=False)


def _system_manager() -> SimpleNamespace:
    return SimpleNamespace(email="admin@example.com", roles=["System Manager"], is_superadmin=False)


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
def test_shipped_doctype_has_permissions_defined(doctype_name):
    dt = _load(doctype_name)
    assert dt.permissions, f"{doctype_name} must declare permissions, not be open by default"


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.parametrize("action", ["read", "write", "create", "delete"])
@pytest.mark.asyncio
async def test_plain_user_has_no_access(doctype_name, action):
    dt = _load(doctype_name)
    assert await permission_checker.check(_plain_user(), dt, action) is False


@pytest.mark.parametrize("doctype_name", list(_DOCTYPE_JSON))
@pytest.mark.asyncio
async def test_system_manager_can_read_only(doctype_name):
    dt = _load(doctype_name)
    admin = _system_manager()
    assert await permission_checker.check(admin, dt, "read") is True
    assert await permission_checker.check(admin, dt, "write") is False
    assert await permission_checker.check(admin, dt, "create") is False
    assert await permission_checker.check(admin, dt, "delete") is False
