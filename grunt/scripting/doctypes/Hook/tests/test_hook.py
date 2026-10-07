"""Tests for the Hook virtual DocType controller."""

import pytest

import grunt.hooks as hooks
from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.scripting.doctypes.Hook import hook as hook_mod
from grunt.scripting.doctypes.Hook.hook import Hook


def _sample_handler():  # pragma: no cover - only its name is used
    pass


@pytest.fixture
def registries(monkeypatch):
    """Populate the in-memory hook registries with a known shape."""
    monkeypatch.setattr(
        hooks, "HOOK_REGISTRY", {"after_migrate": [{"handler": _sample_handler, "priority": 5}]}
    )
    monkeypatch.setattr(
        hooks,
        "DOC_EVENT_REGISTRY",
        {"User": {"before_save": [{"handler": _sample_handler, "priority": 10}]}},
    )
    monkeypatch.setattr(hook_mod, "_collect_server_scripts", _async_return([]))


def _async_return(value):
    async def _inner(*_a, **_kw):
        return value

    return _inner


async def _list(**kwargs):
    return await Hook.get_list("Hook", session=None, user=SYSTEM_USER, **kwargs)


@pytest.mark.asyncio
async def test_get_list_merges_global_and_doctype_hooks(registries):
    result = await _list()

    assert result["meta"]["total"] == 2
    by_event = {r["event"]: r for r in result["data"]}

    assert by_event["after_migrate"]["source"] == "Python (Global)"
    assert by_event["after_migrate"]["reference_doctype"] == "*"
    assert by_event["after_migrate"]["handler"].endswith("_sample_handler")

    assert by_event["before_save"]["source"] == "Python (DocType)"
    assert by_event["before_save"]["reference_doctype"] == "User"
    # name is a stable, readable composite id
    assert by_event["before_save"]["name"] == by_event["before_save"]["id"]
    assert by_event["before_save"]["name"].startswith("User::before_save::")


@pytest.mark.asyncio
async def test_get_list_search_filters_rows(registries):
    result = await _list(search="after_migrate")
    assert [r["event"] for r in result["data"]] == ["after_migrate"]


@pytest.mark.asyncio
async def test_load_returns_single_hook_by_name(registries):
    target = (await _list())["data"][0]
    doc = Hook("Hook", {"name": target["name"]})
    await doc.load_from_db()
    assert doc.data == target


@pytest.mark.asyncio
async def test_load_unknown_raises_404(registries):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await Hook("Hook", {"name": "Nope::nope::nope"}).load_from_db()
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["db_insert", "db_update", "db_delete"])
async def test_writes_are_rejected(registries, op):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await getattr(Hook("Hook", {"name": "x"}), op)()
    assert exc.value.status_code == 405
