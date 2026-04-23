"""Grunt developer API — the primary interface for building apps on the Grunt framework.

This module provides a high-level, async-first API for app developers. It is context-aware: the current
database session, engine, and user are automatically injected via ContextVars that
are set by the framework at the start of each request / lifecycle hook call.
"""

from __future__ import annotations

from grunt.core.app.context_api import ContextAPI
from grunt.core.app.document_api import DocumentAPI
from grunt.core.app.permission_api import PermissionAPI
from grunt.core.app.realtime_api import RealtimeAPI
from grunt.core.app.utility_api import UtilityAPI
from grunt.core.cache.query_cache import QueryCache
from grunt.core.metadata.registry import doctype_registry
from grunt.db import GruntDB
from grunt.errors import GruntError
from grunt.session import GruntSession

# ── Main API ──────────────────────────────────────────────────────────────────


class GruntApp(ContextAPI, RealtimeAPI, PermissionAPI, DocumentAPI, UtilityAPI):
    """Primary developer API for building Grunt apps.

    Accessed via the module-level singleton ``grunt``:

    .. code-block:: python

        from grunt.app import grunt

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
        print(grunt.session.user)
    """

    def __init__(self) -> None:
        self.db = GruntDB()
        self.session = GruntSession()
        self.query_cache = QueryCache()

# ── Module-level singleton ────────────────────────────────────────────────────


grunt = GruntApp()

# Backward-compatible public exports for internal/test imports.
__all__ = ["GruntApp", "GruntDB", "GruntError", "doctype_registry", "grunt"]
