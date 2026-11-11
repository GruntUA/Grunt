"""A cloud storage remote turning from OK to Error fires ``storage_remote_failed``;
the core's subscriber (grunt/core_events.py) notifies the System Managers."""

import pytest

from grunt.events import fire
from grunt.notification.service import notification_service
from grunt.storage.cloud import REMOTE_FAILED


@pytest.mark.asyncio
async def test_remote_failure_notifies_system_managers(ctx, monkeypatch):
    sent: list[dict] = []

    async def recipients(roles, session):
        assert roles == ["System Manager"]
        return ["admin@example.com"]

    async def notify(session, **kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(notification_service, "_resolve_role_recipients", recipients)
    monkeypatch.setattr(notification_service, "notify", notify)

    await fire(
        REMOTE_FAILED,
        doctype="StorageRemote",
        doc_id="Backups",
        message="token expired",
        session=ctx.db._session(),
    )

    assert len(sent) == 1
    assert sent[0]["user"] == "admin@example.com"
    assert sent[0]["doc_id"] == "Backups"
    assert sent[0]["message"] == "token expired"
