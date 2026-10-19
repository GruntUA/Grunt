"""grunt.bulk_update (SDK) stamps modified_at/modified_by on matched rows.

Regression: modified_at was written as an ISO string, which SQLite's
DateTime column rejects - every grunt.bulk_update call failed (e.g.
Notification "mark all read").
"""

from datetime import datetime

import pytest

from grunt.notification.service import notification_service


@pytest.mark.asyncio
async def test_bulk_update_stamps_modified_at(ctx):
    await ctx.new_doc("Role", {"role_name": "Bulk A"})
    await ctx.new_doc("Role", {"role_name": "Bulk B"})

    rows = await ctx.bulk_update(
        "Role", {"role_name__in": ["Bulk A", "Bulk B"]}, {"description": "оновлено"}
    )

    assert rows == 2
    role = await ctx.db.get_doc("Role", "Bulk A")
    assert role["description"] == "оновлено"
    assert isinstance(role["modified_at"], datetime)
    assert role["modified_by"] == "system@grunt.local"


@pytest.mark.asyncio
async def test_mark_all_read(ctx):
    assert await notification_service.mark_all_read("nobody@example.com") == 0
