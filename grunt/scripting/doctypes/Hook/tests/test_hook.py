"""Tests for the Hook virtual DocType controller."""

import pytest

from grunt.scripting.doctypes.Hook import hook as hook_mod
from grunt.scripting.doctypes.Hook.hook import Hook


def _sample_handler():  # pragma: no cover - only its name is used
    pass


@pytest.fixture
def registries(monkeypatch):
    """Populate the in-memory hook registries with a known shape."""
    import grunt.hooks as hooks

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


@pytest.mark.asyncio
async def test_get_list_merges_global_and_doctype_hooks(registries):
    result = await Hook("Hook").get_list()

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
    result = await Hook("Hook").get_list(search="after_migrate")
    assert [r["event"] for r in result["data"]] == ["after_migrate"]


@pytest.mark.asyncio
async def test_get_returns_single_hook_by_name(registries):
    listing = await Hook("Hook").get_list()
    target = listing["data"][0]
    fetched = await Hook("Hook").get(target["name"])
    assert fetched == target


@pytest.mark.asyncio
async def test_get_unknown_raises_404(registries):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await Hook("Hook").get("Nope::nope::nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["create", "update", "delete"])
async def test_mutations_are_rejected(registries, op):
    from fastapi import HTTPException

    ctrl = Hook("Hook")
    args = {"create": ({},), "update": ("x", {}), "delete": ("x",)}[op]
    with pytest.raises(HTTPException) as exc:
        await getattr(ctrl, op)(*args)
    assert exc.value.status_code == 405
