"""Document Actions registry — code registration + metadata binding enrichment.

Actions are registered in app code (`@doc_action`) and bound to a DocType via
its `actions` table. `grunt.actions.run` only executes a key that is BOTH
registered AND bound on that DocType, so the runnable set per DocType is
exactly what the metadata declares.
"""

from __future__ import annotations

import pytest

from grunt.actions import (
    actions_for_doctype,
    enrich_doctype_actions,
    get_doc_action,
    register_doc_action,
)
from grunt.actions.registry import DOC_ACTION_SOURCE, DocAction
from grunt.metadata.doctype import DocType
from grunt.metadata.dynamic_options import get_options


@pytest.fixture
def sample_action():
    async def handler(doc, *, args):
        return {"message": "ok", "seen": doc.get("name"), "args": args}

    action = DocAction(
        key="test.doc_actions.sample",
        label="Sample",
        handler=handler,
        doctypes=["Widget"],
        icon="activity",
        confirm="Sure?",
    )
    register_doc_action(action)
    return action


def test_registering_exposes_key_to_dropdown(sample_action):
    assert sample_action.key in get_options(DOC_ACTION_SOURCE)
    assert get_doc_action(sample_action.key) is sample_action


def test_actions_for_doctype_filters_by_doctypes(sample_action):
    assert sample_action in actions_for_doctype("Widget")
    assert sample_action not in actions_for_doctype("Gadget")


def test_wildcard_action_matches_any_doctype():
    action = DocAction(
        key="test.doc_actions.any",
        label="Any",
        handler=lambda doc, *, args: None,
        doctypes=["*"],
    )
    register_doc_action(action)
    assert action in actions_for_doctype("Anything")


def test_enrich_resolves_defaults_and_flags_missing(sample_action):
    data = {
        "name": "Widget",
        "actions": [
            {"action": sample_action.key},
            {"action": sample_action.key, "label": "Custom", "variant": "destructive"},
            {"action": "test.doc_actions.gone"},
        ],
    }
    from grunt.i18n import use_language

    with use_language("en"):  # labels are translated for the request language
        enrich_doctype_actions(data)

    resolved, overridden, missing = data["actions"]
    assert resolved["_label"] == "Sample"
    assert resolved["_icon"] == "activity"
    assert resolved["_confirm"] == "Sure?"
    assert resolved["_missing"] is False

    assert overridden["_label"] == "Custom"
    assert overridden["_variant"] == "destructive"

    assert missing["_missing"] is True

    assert {c["key"] for c in data["_action_catalog"]} >= {sample_action.key}


def test_enrich_exposes_input_fields():
    """An action that declares `fields` surfaces them as `_fields` on the binding
    and in the catalog, so the toolbar can prompt before running."""
    prompt_fields = [
        {"fieldname": "qty", "label": "How many", "fieldtype": "Float", "required": True},
        {"fieldname": "note", "label": "Note", "fieldtype": "Text"},
    ]
    register_doc_action(
        DocAction(
            key="test.doc_actions.with_fields",
            label="With fields",
            handler=lambda doc, *, args: None,
            doctypes=["Widget"],
            fields=prompt_fields,
        )
    )

    data = {"name": "Widget", "actions": [{"action": "test.doc_actions.with_fields"}]}
    enrich_doctype_actions(data)

    assert data["actions"][0]["_fields"] == prompt_fields
    catalog = {c["key"]: c for c in data["_action_catalog"]}
    assert catalog["test.doc_actions.with_fields"]["fields"] == prompt_fields


def test_incomplete_and_null_action_rows_are_tolerated():
    """The child-table editor sends nulls for empty cells; blank rows are dropped."""
    from grunt.metadata.doctype import DocType

    dt = DocType(
        name="X",
        label="X",
        module="core",
        actions=[
            {"action": None, "label": None},  # half-filled → pruned
            {"action": "core.recalc", "group": None, "variant": None},  # nulls → ""
        ],
    )
    dumped = dt.model_dump()["actions"]
    assert len(dumped) == 1
    assert dumped[0] == {
        "action": "core.recalc",
        "label": "",
        "group": "",
        "variant": "",
        "condition": None,
        "hidden": False,
    }


def test_builtin_core_actions_are_registered():
    for key in ("core.duplicate", "core.recalc", "core.copy_reference"):
        spec = get_doc_action(key)
        assert spec is not None, key
        assert spec.doctypes == ["*"]
        assert spec in actions_for_doctype("AnyDocType")


async def test_run_rejects_unbound_key(sample_action, monkeypatch):
    """A registered but unbound action must not run on a DocType."""
    from grunt import actions as actions_mod

    class _Reg:
        async def get(self, name):
            return DocType(name=name, label=name, module="core", actions=[])

        async def get_meta(self, name):
            from grunt.document.meta import Meta

            return Meta(await self.get(name))

    monkeypatch.setattr("grunt.metadata.registry.doctype_registry", _Reg())

    with pytest.raises(Exception) as exc:
        await actions_mod.run("Widget", sample_action.key, "W-1")
    assert "не підключено" in str(exc.value) or "NOT_FOUND" in str(exc.value)
