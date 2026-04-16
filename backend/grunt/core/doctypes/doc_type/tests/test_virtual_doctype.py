"""Tests for Virtual DocType — base class and delegation logic."""

import pytest

from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.virtual import VirtualDocType


class TestVirtualDocTypeBase:
    def test_init(self):
        vdt = VirtualDocType("ExternalCustomer", user="admin@test.com")
        assert vdt.doctype == "ExternalCustomer"
        assert vdt.user == "admin@test.com"

    @pytest.mark.asyncio
    async def test_get_list_not_implemented(self):
        vdt = VirtualDocType("Test")
        with pytest.raises(NotImplementedError, match="get_list"):
            await vdt.get_list()

    @pytest.mark.asyncio
    async def test_get_not_implemented(self):
        vdt = VirtualDocType("Test")
        with pytest.raises(NotImplementedError, match="get"):
            await vdt.get("123")

    @pytest.mark.asyncio
    async def test_create_not_implemented(self):
        vdt = VirtualDocType("Test")
        with pytest.raises(NotImplementedError, match="create"):
            await vdt.create({"name": "x"})

    @pytest.mark.asyncio
    async def test_update_not_implemented(self):
        vdt = VirtualDocType("Test")
        with pytest.raises(NotImplementedError, match="update"):
            await vdt.update("123", {"name": "y"})

    @pytest.mark.asyncio
    async def test_delete_not_implemented(self):
        vdt = VirtualDocType("Test")
        with pytest.raises(NotImplementedError, match="delete"):
            await vdt.delete("123")


class TestVirtualDocTypeSubclass:
    """Test a concrete implementation of VirtualDocType."""

    @pytest.mark.asyncio
    async def test_custom_get_list(self):
        class MockAPI(VirtualDocType):
            async def get_list(self, **kwargs):
                return {
                    "data": [{"id": "1", "name": "Customer A"}],
                    "meta": {"total": 1, "page": 1, "per_page": 20},
                }

        ctrl = MockAPI("ExternalCustomer")
        result = await ctrl.get_list()
        assert result["data"][0]["name"] == "Customer A"
        assert result["meta"]["total"] == 1

    @pytest.mark.asyncio
    async def test_custom_get(self):
        class MockAPI(VirtualDocType):
            async def get(self, doc_id, **kwargs):
                return {"id": doc_id, "name": f"Customer {doc_id}"}

        ctrl = MockAPI("ExternalCustomer")
        result = await ctrl.get("42")
        assert result["id"] == "42"
        assert result["name"] == "Customer 42"

    @pytest.mark.asyncio
    async def test_custom_create(self):
        class MockAPI(VirtualDocType):
            async def create(self, data, **kwargs):
                return {"id": "new-1", **data}

        ctrl = MockAPI("ExternalCustomer")
        result = await ctrl.create({"name": "New Customer"})
        assert result["id"] == "new-1"
        assert result["name"] == "New Customer"

    @pytest.mark.asyncio
    async def test_custom_update(self):
        class MockAPI(VirtualDocType):
            async def update(self, doc_id, data, **kwargs):
                return {"id": doc_id, **data}

        ctrl = MockAPI("ExternalCustomer")
        result = await ctrl.update("42", {"name": "Updated"})
        assert result["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_custom_delete(self):
        class MockAPI(VirtualDocType):
            _deleted = []

            async def delete(self, doc_id, **kwargs):
                self._deleted.append(doc_id)

        ctrl = MockAPI("ExternalCustomer")
        await ctrl.delete("42")
        assert "42" in ctrl._deleted

    @pytest.mark.asyncio
    async def test_get_count_default(self):
        class MockAPI(VirtualDocType):
            async def get_list(self, **kwargs):
                return {
                    "data": [],
                    "meta": {"total": 42, "page": 1, "per_page": 1},
                }

        ctrl = MockAPI("ExternalCustomer")
        count = await ctrl.get_count()
        assert count == 42


class TestDocTypeIsVirtual:
    def test_default_is_false(self):
        dt = DocType(name="Test", label="Test", module="core")
        assert dt.is_virtual is False

    def test_can_set_true(self):
        dt = DocType(name="Test", label="Test", module="core", is_virtual=True)
        assert dt.is_virtual is True
