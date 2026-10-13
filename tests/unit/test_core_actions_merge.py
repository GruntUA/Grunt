"""Core DocType sync (`_inject_core`) merges new action bindings from the JSON source."""

from __future__ import annotations

from grunt.metadata.doctype import DocType
from grunt.metadata.registry import DocTypeRegistry


def _dt(actions: list[dict]) -> DocType:
    return DocType.model_validate(
        {"name": "X", "label": "X", "module": "core", "fields": [], "actions": actions}
    )


def test_new_json_actions_are_appended():
    stored = _dt([{"action": "a.one"}])
    source = _dt([{"action": "a.one"}, {"action": "a.two", "variant": "outline"}])

    added = DocTypeRegistry._merge_core_actions(stored, source)

    assert added == ["a.two"]
    assert [a.action for a in stored.actions] == ["a.one", "a.two"]
    assert stored.actions[1].variant == "outline"


def test_stored_overrides_are_kept():
    stored = _dt([{"action": "a.one", "label": "Custom", "hidden": True}])
    source = _dt([{"action": "a.one", "label": ""}])

    assert DocTypeRegistry._merge_core_actions(stored, source) == []
    assert stored.actions[0].label == "Custom"
    assert stored.actions[0].hidden is True
