"""Tests for the Hook virtual DocType's store."""

import pytest

import grunt
import grunt.hooks as hooks
from grunt.query.query import Query
from grunt.scripting.doctypes.Hook import hook as hook_mod
from grunt.scripting.doctypes.Hook.hook import HookStore


def _sample_handler():  # pragma: no cover - only its name is used
    pass


@pytest.fixture
def registries(ctx, monkeypatch):
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


async def _store() -> HookStore:
    """The store with the Hook DocType's real settings (search fields, sort)."""
    return HookStore(await grunt.get_meta("Hook"), grunt.get_session())


async def _list(search: str | None = None) -> dict:
    query = Query("Hook", search=search)
    store = await _store()
    return {"data": await store.fetch(query), "meta": {"total": await store.count(query)}}


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
    assert await (await _store()).get(target["name"]) == target


@pytest.mark.asyncio
async def test_load_unknown_is_none(registries):
    assert await (await _store()).get("Nope::nope::nope") is None


def test_writes_are_not_supported():
    assert not HookStore.capabilities
