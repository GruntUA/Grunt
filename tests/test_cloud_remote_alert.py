"""A cloud storage remote turning from OK to Error fires ``storage_remote_failed``;
the core's subscriber (grunt/core_events.py) notifies the System Managers."""

import pytest

from grunt.events import fire
from grunt.storage.cloud import REMOTE_FAILED

# Code events notify through the core's standard Notification rules.
pytestmark = pytest.mark.usefixtures("standard_notifications")


@pytest.mark.asyncio
async def test_remote_failure_notifies_system_managers(ctx):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.new_doc(
            "User",
            {
                "email": "admin@example.com",
                "first_name": "Ад",
                "last_name": "Мін",
                "roles": [{"role_name": "System Manager"}],
            },
        )
        await fire(
            REMOTE_FAILED,
            doctype="StorageRemote",
            doc_id="Backups",
            message="token expired",
            session=ctx.db._session(),
        )
        sent = await ctx.db.get_all(
            "NotificationLog",
            filters={"user": "admin@example.com"},
            fields=["ref_doctype", "doc_id", "message"],
        )

    assert sent == [
        {"ref_doctype": "StorageRemote", "doc_id": "Backups", "message": "token expired"}
    ]
