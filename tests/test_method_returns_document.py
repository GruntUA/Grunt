"""Controllers at the RPC boundary: returned as ``doc.as_dict()``, never accepted from JSON."""

import sys
import types

import grunt
from grunt.api.v1.method import _documents_as_dicts
from grunt.document.base import Document

MOD = "tg_returns_document"


def _note(**data) -> Document:
    return Document(doctype="Note", data={"name": "N1", "title": "Hi", **data})


def test_controllers_become_their_json_anywhere_in_the_result():
    out = _documents_as_dicts({"doc": _note(), "rows": [_note(name="N2")], "n": 1})
    assert out == {
        "doc": {"doctype": "Note", "name": "N1", "title": "Hi"},
        "rows": [{"doctype": "Note", "name": "N2", "title": "Hi"}],
        "n": 1,
    }


def test_results_without_controllers_are_not_copied():
    rows = [{"a": 1}, {"b": [2, 3]}]
    assert _documents_as_dicts(rows) is rows


async def test_returned_controller_does_not_leak_its_internals(client, auth_headers, monkeypatch):
    @grunt.whitelist()
    async def note() -> Document:
        # Bound to the caller - encoded as an object, `user` (with its
        # password hash) and `session` would go out with it.
        return Document(doctype="Note", data={"name": "N1", "title": "Hi"})

    module = types.ModuleType(MOD)
    module.note = note
    monkeypatch.setitem(sys.modules, MOD, module)

    resp = await client.get(f"/api/v1/method/{MOD}.note", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"doctype": "Note", "name": "N1", "title": "Hi"}
    assert "hashed_password" not in resp.text


async def test_controller_typed_parameter_is_refused_over_http(client, auth_headers):
    """`user: User | None` is for Python callers - JSON would arrive as a forged dict."""
    forged = {"id": "victim@grunt.example.com", "roles": ["System Manager"]}
    resp = await client.post(
        "/api/v1/method/grunt.auth.doctypes.ApiKey.api_key.create_api_key",
        json={"label": "x", "user": forged},
        headers=auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "user" in resp.text
