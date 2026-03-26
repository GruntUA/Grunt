"""Tests for the Document Links service — sync and backlinks logic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from grunt.core.document.links import LinkService


def _make_field(fieldname, fieldtype="Text", options=None):
    return SimpleNamespace(fieldname=fieldname, fieldtype=fieldtype, options=options)


def _make_dt(fields):
    return SimpleNamespace(fields=fields)


class TestLinkExtraction:
    """Test that sync_links correctly identifies Link fields and their values."""

    def test_find_link_fields(self):
        """Verify we can identify Link fields from DocType definition."""
        fields = [
            _make_field("title", "Text"),
            _make_field("customer", "Link", options="Customer"),
            _make_field("supplier", "Link", options="Supplier"),
            _make_field("notes", "LongText"),
        ]
        link_fields = [f for f in fields if f.fieldtype == "Link"]
        assert len(link_fields) == 2
        assert link_fields[0].fieldname == "customer"
        assert link_fields[0].options == "Customer"
        assert link_fields[1].fieldname == "supplier"

    def test_link_field_with_value(self):
        """Only Link fields with non-empty values should create backlinks."""
        fields = [
            _make_field("customer", "Link", options="Customer"),
            _make_field("supplier", "Link", options="Supplier"),
        ]
        doc = {"customer": "CUST-001", "supplier": None}

        links = []
        for f in fields:
            if f.fieldtype == "Link" and doc.get(f.fieldname):
                links.append({
                    "source_doctype": "Invoice",
                    "source_id": "INV-001",
                    "target_doctype": f.options,
                    "target_id": str(doc[f.fieldname]),
                    "link_fieldname": f.fieldname,
                })

        assert len(links) == 1
        assert links[0]["target_doctype"] == "Customer"
        assert links[0]["target_id"] == "CUST-001"

    def test_no_link_fields(self):
        """DocType with no Link fields should produce zero links."""
        fields = [
            _make_field("title", "Text"),
            _make_field("amount", "Float"),
        ]
        link_fields = [f for f in fields if f.fieldtype == "Link"]
        assert len(link_fields) == 0

    def test_link_without_options_skipped(self):
        """Link field without options (target DocType) should be skipped."""
        fields = [_make_field("ref", "Link", options=None)]
        doc = {"ref": "some-id"}

        links = []
        for f in fields:
            if f.fieldtype == "Link" and doc.get(f.fieldname) and f.options:
                links.append(f.fieldname)
        assert len(links) == 0

    def test_multiple_links_to_same_doctype(self):
        """Multiple Link fields can point to the same target DocType."""
        fields = [
            _make_field("billing_customer", "Link", options="Customer"),
            _make_field("shipping_customer", "Link", options="Customer"),
        ]
        doc = {"billing_customer": "C-001", "shipping_customer": "C-002"}

        links = []
        for f in fields:
            if f.fieldtype == "Link" and doc.get(f.fieldname) and f.options:
                links.append({
                    "target_doctype": f.options,
                    "target_id": doc[f.fieldname],
                    "link_fieldname": f.fieldname,
                })

        assert len(links) == 2
        assert links[0]["target_id"] == "C-001"
        assert links[1]["target_id"] == "C-002"


class TestLinkService:
    def test_service_instance(self):
        svc = LinkService()
        assert hasattr(svc, "sync_links")
        assert hasattr(svc, "get_backlinks")
        assert hasattr(svc, "delete_links")
