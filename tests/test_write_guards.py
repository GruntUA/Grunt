"""``write_guards`` (hooks.py): app code that vetoes updating or deleting a document,
and ``doctype_js``: an app's client scripts on other DocTypes' forms."""

import pytest

import grunt
from grunt.apps.consumers import HOOK_CONSUMERS, LoadContext
from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.document import guards
from grunt.errors import APIError
from grunt.scripting import file_scripts
from tests.support import make_user

NOTE = {
    "name": "GuardNote",
    "label": "Guard Note",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "frozen", "label": "Frozen", "fieldtype": "Check"},
    ],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
    ],
}

calls: list[tuple[str, str, dict]] = []


async def freeze(action, doctype, existing, changes, user):
    calls.append((action, doctype, dict(changes)))
    if doctype == "GuardNote" and existing.get("frozen") and changes.get("frozen") != 0:
        grunt.throw(f"frozen: no {action}")


@pytest.fixture
def guard():
    saved = list(guards._GUARDS)
    guards._GUARDS.clear()
    calls.clear()
    ctx = LoadContext(app_name="testapp", app_dir=None, fastapi_app=None)  # type: ignore[arg-type]
    HOOK_CONSUMERS["write_guards"].apply([f"{__name__}.freeze"], ctx)
    yield
    guards._GUARDS[:] = saved


@pytest.fixture
async def note(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**NOTE, "__is_new": True})
    doc = await ctx.new_doc("GuardNote", {"title": "Budget", "frozen": 1})
    await ctx.db._session().commit()
    return doc


@pytest.mark.asyncio
async def test_guard_vetoes_update_and_delete(guard, note, db_session, engine):
    async with grunt.context(db_session, engine, make_user("ann@example.com", is_superadmin=True)):
        with pytest.raises(APIError, match="frozen: no update"):
            await grunt.save_doc("GuardNote", note["name"], {"title": "Changed"})
        with pytest.raises(APIError, match="frozen: no delete"):
            await grunt.delete_doc("GuardNote", note["name"])
        # the guard decides by the change itself
        await grunt.save_doc("GuardNote", note["name"], {"frozen": 0})
        await grunt.save_doc("GuardNote", note["name"], {"title": "Changed"})
    assert calls[0] == ("update", "GuardNote", {"title": "Changed"})
    assert calls[1] == ("delete", "GuardNote", {})


@pytest.mark.asyncio
async def test_system_user_is_not_guarded(guard, note, db_session, engine):
    async with grunt.context(db_session, engine, SYSTEM_USER):
        await grunt.save_doc("GuardNote", note["name"], {"title": "By system"})
    assert calls == []


def test_doctype_js_adds_app_scripts_after_global_ones(tmp_path, monkeypatch):
    (tmp_path / "desk").mkdir()
    (tmp_path / "desk" / "every.js").write_text("function on_load(frm) {}")
    (tmp_path / "desk" / "todo.js").write_text("function on_load(frm) { /* todo */ }")
    monkeypatch.setattr(file_scripts, "_DOCTYPE_JS", {})
    ctx = LoadContext(app_name="testapp", app_dir=tmp_path, fastapi_app=None)
    HOOK_CONSUMERS["doctype_js"].apply({"*": ["desk/every.js"], "ToDo": "desk/todo.js"}, ctx)

    names = [s["name"] for s in file_scripts.get_file_client_scripts("ToDo")]
    assert names[:2] == ["grunt:global_form.js", "grunt:global_list.js"]
    assert names[2:4] == ["testapp:every.js", "testapp:todo.js"]
    assert "testapp:todo.js" not in [
        s["name"] for s in file_scripts.get_file_client_scripts("User")
    ]
