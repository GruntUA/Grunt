"""Unit tests for grunt.notification.rule_index — the gate that stops every
document write from queuing a notification-evaluation worker task.
"""

from __future__ import annotations

import pytest

from grunt.notification import rule_index


@pytest.fixture(autouse=True)
def _reset_index():
    rule_index.invalidate()
    rule_index._loaded_at = 0.0
    yield
    rule_index.invalidate()
    rule_index._loaded_at = 0.0


@pytest.mark.asyncio
async def test_has_rules_true_only_for_indexed_pairs(monkeypatch):
    async def fake_load():
        return frozenset({("Order", "after_save"), ("Invoice", "after_insert")})

    monkeypatch.setattr(rule_index, "_load", fake_load)

    assert await rule_index.has_rules("Order", "after_save") is True
    assert await rule_index.has_rules("Invoice", "after_insert") is True
    # right doctype, wrong event
    assert await rule_index.has_rules("Order", "after_insert") is False
    # unknown doctype
    assert await rule_index.has_rules("Comment", "after_save") is False


@pytest.mark.asyncio
async def test_snapshot_is_cached_between_calls(monkeypatch):
    calls = 0

    async def fake_load():
        nonlocal calls
        calls += 1
        return frozenset({("Order", "after_save")})

    monkeypatch.setattr(rule_index, "_load", fake_load)

    await rule_index.has_rules("Order", "after_save")
    await rule_index.has_rules("Order", "after_save")
    assert calls == 1


@pytest.mark.asyncio
async def test_invalidate_forces_reload(monkeypatch):
    calls = 0

    async def fake_load():
        nonlocal calls
        calls += 1
        return frozenset({("Order", "after_save")})

    monkeypatch.setattr(rule_index, "_load", fake_load)

    await rule_index.has_rules("Order", "after_save")
    rule_index.invalidate_on_change()  # doc-event hook target
    await rule_index.has_rules("Order", "after_save")
    assert calls == 2


@pytest.mark.asyncio
async def test_fails_open_when_no_session(monkeypatch):
    async def fake_load():
        return None

    monkeypatch.setattr(rule_index, "_load", fake_load)
    assert await rule_index.has_rules("Order", "after_save") is True


@pytest.mark.asyncio
async def test_fails_open_on_load_error(monkeypatch):
    async def fake_load():
        raise RuntimeError("db down")

    monkeypatch.setattr(rule_index, "_load", fake_load)
    assert await rule_index.has_rules("Order", "after_save") is True
