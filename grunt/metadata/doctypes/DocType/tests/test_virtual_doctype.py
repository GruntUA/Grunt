"""The base ``Store`` - a virtual DocType without a store of its own stores nothing."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from grunt.metadata.doctype import DocType
from grunt.query.query import Query
from grunt.store import Store


def _store() -> Store:
    return Store(SimpleNamespace(name="ExternalCustomer"), None)  # type: ignore[arg-type]


class TestStorageDefaults:
    @pytest.mark.asyncio
    async def test_nothing_to_load(self):
        assert await _store().get("42") is None

    @pytest.mark.asyncio
    async def test_writes_are_405(self):
        store = _store()
        writes = (
            lambda: store.insert({"name": "42"}, input={}, user=None),  # type: ignore[arg-type]
            lambda: store.update("42", {}, before={"name": "42"}, input={}, user=None),  # type: ignore[arg-type]
            lambda: store.delete("42", before={"name": "42"}),
        )
        for write in writes:
            with pytest.raises(HTTPException) as exc:
                await write()
            assert exc.value.status_code == 405

    @pytest.mark.asyncio
    async def test_list_is_empty(self):
        store = _store()
        assert await store.fetch(Query("ExternalCustomer")) == []
        assert await store.count(Query("ExternalCustomer")) == 0

    def test_can_nothing(self):
        assert not _store().capabilities


class TestDocTypeIsVirtual:
    def test_default_is_false(self):
        dt = DocType(name="Test", label="Test", module="core")
        assert dt.is_virtual is False

    def test_can_set_true(self):
        dt = DocType(name="Test", label="Test", module="core", is_virtual=True)
        assert dt.is_virtual is True
