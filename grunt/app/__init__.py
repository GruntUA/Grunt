"""Grunt developer API - the primary interface for building apps on the Grunt framework.

This module provides a high-level, async-first API for app developers.
It is context-aware: the current
database session, engine, and user are automatically injected via ContextVars that
are set by the framework at the start of each request / lifecycle hook call.
"""

from __future__ import annotations

from grunt.app.context_api import ContextAPI
from grunt.app.document_api import DocumentAPI
from grunt.app.permission_api import PermissionAPI
from grunt.app.realtime_api import RealtimeAPI
from grunt.app.utility_api import UtilityAPI
from grunt.cache.document_cache import DocumentCache
from grunt.cache.query_cache import QueryCache
from grunt.db import GruntDB
from grunt.metadata.registry import doctype_registry

# Main API


class GruntApp(ContextAPI, RealtimeAPI, PermissionAPI, DocumentAPI, UtilityAPI):
    """Primary developer API for building Grunt apps.

    Its methods are re-exported by the ``grunt`` package - app code uses them
    from there:

    .. code-block:: python

        import grunt

        # CRUD
        doc = await grunt.get_doc("Invoice", invoice_id)
        new_invoice = await grunt.new_doc("Invoice", {"number": "INV-001", "amount": 1500.0})
        updated = await grunt.save_doc("Invoice", invoice_id, {"status": "Paid"})
        await grunt.delete_doc("Invoice", invoice_id)

        # List / count
        items = await grunt.get_list("Product", filters={"active": True}, limit=50)
        total = await grunt.count("Product", filters={"active": True})

        # DB shortcuts
        name = await grunt.db.get_value("Customer", customer_id, "full_name")
        await grunt.db.set_value("Invoice", invoice_id, "status", "Paid")

        # Meta
        meta = await grunt.get_meta("Invoice")

        # Notifications
        await grunt.notify(users=["user@example.com"], subject="Paid", message="...")
        await grunt.publish(user="user@example.com", event="msgprint", message="Done")

        # Error handling
        grunt.throw("Validation failed")

        # Current user
        print(grunt.get_user().email)
    """

    def __init__(self) -> None:
        self.db = GruntDB()
        self.query_cache = QueryCache()
        self.doc_cache = DocumentCache()


# Module-level singleton


grunt = GruntApp()

__all__ = ["GruntApp", "GruntDB", "doctype_registry", "grunt"]
