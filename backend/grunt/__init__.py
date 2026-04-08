"""Ґрунт — Python Framework for Building CMS, ERP, and Business Apps.

Primary imports for app developers:
    from grunt import db, msgprint, throw, notify, can_read, can_write

Example usage in a DocType controller:
    from grunt import db, msgprint, get_current_user, can_read
    from grunt.app import grunt

    class Invoice:
        async def before_save(self):
            # Get related document
            order = await grunt.get_doc("Order", self.doc.order_id)

            # Check business rule
            if await db.exists("Lock", self.doc.id):
                throw("This invoice is locked")

            # Check permissions
            current_user = await get_current_user()
            if not await can_write("Contract", self.doc.contract_id):
                throw("Read-only access")

            # Notify user
            msgprint(f"Amount: {self.doc.total}", type="success")
"""


# Lazy loading to avoid circular imports
def __getattr__(name: str):
    """Lazy load API exports when first accessed."""
    if name in (
        "db",
        "GruntDB",
        "msgprint",
        "msgprint_list",
        "throw",
        "notify",
        "notify_all",
        "queue_email",
        "ApplicationError",
        "can_read",
        "can_write",
        "can_submit",
        "can_delete",
        "can_create",
        "get_current_user",
        "add_comment",
        "get_comments",
        "delete_comment",
        "log_activity",
        "get_activity_log",
        "Comment",
        "ActivityEntry",
        "set_session",
        "get_session",
        "set_user",
        "get_user",
        "set_engine",
        "get_engine",
        "set_site",
        "get_site",
        "clear_context",
    ):
        from grunt import api  # noqa: PLC0415

        return getattr(api, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "db",
    "GruntDB",
    "msgprint",
    "msgprint_list",
    "throw",
    "notify",
    "notify_all",
    "queue_email",
    "ApplicationError",
    "can_read",
    "can_write",
    "can_submit",
    "can_delete",
    "can_create",
    "get_current_user",
    "add_comment",
    "get_comments",
    "delete_comment",
    "log_activity",
    "get_activity_log",
    "Comment",
    "ActivityEntry",
    "set_session",
    "get_session",
    "set_user",
    "get_user",
    "set_engine",
    "get_engine",
    "set_site",
    "get_site",
    "clear_context",
]
