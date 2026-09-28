"""Grunt High-Level Python API for App Developers.

Simplifies access to documents, database, messages, and notifications without
needing to import and manage session/user/engine manually.

Usage in your app:

    from grunt import db, msgprint, throw, notify, get_current_user

    class MyDocType:
        async def before_save(self):
            # Get another document
            from grunt.app import grunt
            user = await grunt.get_doc("User", self.doc.owner)

            # Check a value
            if await db.exists("Contract", self.doc.contract_id):
                msgprint("Contract linked")
            else:
                throw("Contract not found")

            # Check permissions
            if not await grunt.has_permission("Contact", "read", self.doc.contact_id):
                throw("No permission to access this contact")

            # Save changes
            self.doc["status"] = "Active"
            await self.save()

            # Send notification
            await notify("Update", f"{self.doc.name} was processed")
"""

from typing import TYPE_CHECKING

from grunt.api.context import (
    clear_context,
    get_engine,
    get_session,
    get_site,
    get_user,
    set_engine,
    set_session,
    set_site,
    set_user,
    whitelist,
)
from grunt.api.messages import (
    ApplicationError,
    msgprint,
    msgprint_list,
    notify,
    notify_all,
    queue_email,
    throw,
)
from grunt.api.permissions import get_current_user

if TYPE_CHECKING:
    from grunt.app import GruntDB

    db: GruntDB


def __getattr__(name: str):
    """Lazily resolve ``db``/``GruntDB`` on first access.

    ``grunt.app`` transitively imports ``grunt.document.base``, whose mixins
    decorate their RPC methods with ``@grunt.whitelist()`` — which itself
    imports this package. Importing ``grunt.app`` eagerly here would close
    that loop while ``grunt.app`` is still mid-import (whichever side started
    first ends up importing a partially-initialized module). Deferring it
    until ``db``/``GruntDB`` is actually used breaks the cycle: by the time
    anything asks for a document, both packages have long finished loading.
    """
    if name in ("db", "GruntDB"):
        from grunt.app import GruntDB

        globals()["GruntDB"] = GruntDB
        globals()["db"] = GruntDB()
        return globals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Database API
    "db",
    "GruntDB",
    # Messages
    "msgprint",
    "msgprint_list",
    "throw",
    "notify",
    "notify_all",
    "queue_email",
    "ApplicationError",
    # Permissions
    "get_current_user",
    # Context (internal)
    "set_session",
    "get_session",
    "set_user",
    "get_user",
    "set_engine",
    "get_engine",
    "set_site",
    "get_site",
    "clear_context",
    "whitelist",
]
