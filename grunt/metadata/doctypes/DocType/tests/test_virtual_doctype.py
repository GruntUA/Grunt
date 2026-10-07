"""BaseDocument storage defaults - what a virtual DocType controller overrides."""

import pytest
from fastapi import HTTPException

from grunt.auth.doctypes.User.user import SYSTEM_USER
from grunt.document.base import BaseDocument, DocumentList
from grunt.metadata.doctype import DocType


class TestStorageDefaults:
    @pytest.mark.asyncio
    async def test_load_without_storage_is_404(self):
        doc = BaseDocument("ExternalCustomer", {"name": "42"})
        with pytest.raises(HTTPException) as exc:
            await doc.load_from_db()
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["db_insert", "db_update", "db_delete"])
    async def test_writes_without_storage_are_405(self, method):
        doc = BaseDocument("ExternalCustomer", {"name": "42"})
        with pytest.raises(HTTPException) as exc:
            await getattr(doc, method)()
        assert exc.value.status_code == 405

    @pytest.mark.asyncio
    async def test_list_without_storage_is_empty(self):
        result = await BaseDocument.get_list("ExternalCustomer", session=None, user=SYSTEM_USER)
        assert list(result) == []
        assert result.meta["total"] == 0

    @pytest.mark.asyncio
    async def test_get_count_reads_list_total(self):
        class External(BaseDocument):
            @classmethod
            async def get_list(cls, doctype, *, page=1, per_page=20, **kwargs):
                return DocumentList([], {"total": 42, "page": page, "per_page": per_page})

        assert await External.get_count("ExternalCustomer", session=None, user=SYSTEM_USER) == 42


class TestDocTypeIsVirtual:
    def test_default_is_false(self):
        dt = DocType(name="Test", label="Test", module="core")
        assert dt.is_virtual is False

    def test_can_set_true(self):
        dt = DocType(name="Test", label="Test", module="core", is_virtual=True)
        assert dt.is_virtual is True
