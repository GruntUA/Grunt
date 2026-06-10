"""Grunt High-Level Python API for App Developers.

Simplifies access to documents, database, messages, and notifications without
needing to import and manage session/user/engine manually.

Usage in your app:

    from grunt import db, msgprint, throw, notify, get_current_user, can_read

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
            if not await can_read("Contact", self.doc.contact_id):
                throw("No permission to access this contact")

            # Save changes
            self.doc["status"] = "Active"
            await self.save()

            # Send notification
            await notify("Update", f"{self.doc.name} was processed")
"""

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
from grunt.api.permissions import (
    can_create,
    can_delete,
    can_read,
    can_submit,
    can_write,
    get_current_user,
)
from grunt.app import GruntDB

db = GruntDB()
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
    "can_read",
    "can_write",
    "can_submit",
    "can_delete",
    "can_create",
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
