"""``Notification`` rules: recipient and channel rows, Jinja text (NOTIFICATIONS_PLAN step 2)."""

import importlib
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.notification.service import notification_service

TICKET = {
    "name": "NotifTicket",
    "label": "Ticket",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "priority", "label": "Priority", "fieldtype": "Data"},
        {"fieldname": "manager", "label": "Manager", "fieldtype": "Data"},
        {"fieldname": "client", "label": "Client", "fieldtype": "Link", "options": "User"},
    ],
    "permissions": [{"role": "System Manager", "actions": ["read", "write", "create", "delete"]}],
}

ACTOR = "actor@grunt.example.com"
OWNER = "owner@grunt.example.com"
REVIEWER = "reviewer@grunt.example.com"
CLIENT = "client@grunt.example.com"
ROLE = "Ticket Reviewer"


@pytest.fixture
async def tickets(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**TICKET, "__is_new": True})
    await ctx.new_doc("Role", {"role_name": ROLE})
    for email, first, roles in (
        (ACTOR, "Ада", []),
        (REVIEWER, "Рев", [{"role_name": ROLE}]),
        (CLIENT, "Кліє", []),
    ):
        await ctx.new_doc(
            "User", {"email": email, "first_name": first, "last_name": "Т", "roles": roles}
        )
    await ctx.new_doc(
        "EmailAccount", {"email_address": "out@grunt.example.com", "enable_outgoing": True}
    )
    await ctx.db._session().commit()


async def _rule(ctx, **values):
    return await ctx.new_doc(
        "Notification",
        {
            "ref_doctype": "NotifTicket",
            "event": "after_save",
            "recipients": [{"kind": "Author"}],
            "channels": [{"channel": "in_app"}],
            "subject_template": "{{ doc.title }}",
            "message_template": "",
            **values,
        },
    )


async def _ticket(ctx, **values) -> dict:
    return {
        "name": "T-1",
        "owner": OWNER,
        "title": "Зламався принтер",
        "priority": "High",
        "manager": REVIEWER,
        "client": CLIENT,
        **values,
    }


async def _deliveries(ctx) -> list[tuple[str, str, str]]:
    rows = await ctx.db.get_all(
        "NotificationDelivery",
        fields=["recipient", "channel", "subject"],
        limit=100,
    )
    return sorted((r["recipient"], r["channel"], r["subject"]) for r in rows)


async def _run(ctx, rule, doc, *, extra=None) -> int:
    return await notification_service.apply_rule(
        ctx.db._session(), dict(rule), "NotifTicket", doc, ACTOR, "after_save", extra=extra
    )


@pytest.mark.asyncio
async def test_every_recipient_kind(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.new_doc(
            "ToDo",
            {
                "description": "Розібратися",
                "reference_doctype": "NotifTicket",
                "reference_id": "T-1",
                "assigned_to": "assignee@grunt.example.com",
                "status": "Open",
            },
        )
        await ctx.db.insert_one(
            "DocFollow",
            {
                "name": "f1",
                "owner": "follower@grunt.example.com",
                "reference_doctype": "NotifTicket",
                "reference_id": "T-1",
                "user": "follower@grunt.example.com",
            },
        )
        rule = await _rule(
            ctx,
            recipients=[
                {"kind": "Author"},
                {"kind": "Role", "role": ROLE},
                {"kind": "User", "user": CLIENT},
                {"kind": "Document field", "field": "manager"},
                {"kind": "Document field", "field": "client.email"},
                {"kind": "Email", "email": "boss@grunt.example.com"},
                {"kind": "Assignees"},
                {"kind": "Followers"},
                # Row conditions: this one is false for the ticket.
                {
                    "kind": "Email",
                    "email": "low@grunt.example.com",
                    "condition": "doc.priority == 'Low'",
                },
            ],
        )
        sent = await _run(ctx, rule, await _ticket(ctx))
        recipients = {r for r, _c, _s in await _deliveries(ctx)}

    assert recipients == {
        OWNER,
        REVIEWER,
        CLIENT,
        "boss@grunt.example.com",
        "assignee@grunt.example.com",
        "follower@grunt.example.com",
    }
    assert sent == len(recipients)


@pytest.mark.asyncio
async def test_actor_is_left_out_unless_asked(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rule = await _rule(ctx, recipients=[{"kind": "Email", "email": ACTOR}])
        assert await _run(ctx, rule, await _ticket(ctx)) == 0
        rule = await _rule(ctx, recipients=[{"kind": "Email", "email": ACTOR}], notify_actor=True)
        assert await _run(ctx, rule, await _ticket(ctx)) == 1


@pytest.mark.asyncio
async def test_rule_condition(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rule = await _rule(ctx, condition="doc.priority == 'High'")
        assert await _run(ctx, rule, await _ticket(ctx, priority="Low")) == 0
        assert await _run(ctx, rule, await _ticket(ctx)) == 1


@pytest.mark.asyncio
async def test_channel_with_its_own_text(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rule = await _rule(
            ctx,
            channels=[
                {"channel": "in_app"},
                {"channel": "email", "subject": "[Заявка] {{ doc.title }} від {{ actor }}"},
            ],
        )
        await _run(ctx, rule, await _ticket(ctx))
        rows = await _deliveries(ctx)
        mail = await ctx.db.get_all("EmailQueue", filters={"recipient": OWNER}, fields=["subject"])

    assert rows == [
        (OWNER, "email", "[Заявка] Зламався принтер від Т Ада"),
        (OWNER, "in_app", "Зламався принтер"),
    ]
    assert mail == [{"subject": "[Заявка] Зламався принтер від Т Ада"}]


@pytest.mark.asyncio
async def test_transition_variables(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        rule = await _rule(
            ctx,
            subject_template="{{ action }}: {{ from_state }} → {{ to_state }}",
            message_template="{{ comment }}\n{{ url }}",
        )
        await _run(
            ctx,
            rule,
            await _ticket(ctx),
            extra={
                "action": "Повернути",
                "from_state": "Нова",
                "to_state": "Чернетка",
                "comment": "Додайте фото",
            },
        )
        bell = await ctx.db.get_all(
            "NotificationLog", filters={"user": OWNER}, fields=["subject", "message"]
        )

    assert bell[0]["subject"] == "Повернути: Нова → Чернетка"
    assert bell[0]["message"].startswith("Додайте фото\n")
    assert bell[0]["message"].rstrip().endswith("/NotifTicket/T-1")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"recipients": []}, None),
        ({"channels": []}, None),
        ({"channels": [{"channel": "pigeon"}]}, "pigeon"),
        ({"subject_template": "{{ doc.title"}, "end of template"),
        ({"condition": "doc.priority =="}, "doc.priority =="),
        ({"recipients": [{"kind": "Author", "condition": "and or"}]}, "and or"),
    ],
)
@pytest.mark.asyncio
async def test_form_validation(ctx, tickets, values, message):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        with pytest.raises((ApplicationError, HTTPException)) as exc:
            await _rule(ctx, **values)
    assert exc.value.status_code == 422 if isinstance(exc.value, HTTPException) else True
    if message:  # the text is translated; the variable part is not
        detail = exc.value.detail if isinstance(exc.value, HTTPException) else exc.value
        assert message in str(detail)


migration = importlib.import_module("grunt.db.migrations.versions.0023_notification_rows")


def test_to_jinja():
    assert (
        migration.to_jinja("{doctype}: {name} ({status}) {{ keep }}")
        == "{{ doctype }}: {{ doc.name }} ({{ doc.status }}) {{ keep }}"
    )
    assert migration.recipient_rows("owner, role:Manager, {field:manager}, a@b.c, junk") == [
        {"kind": "Author"},
        {"kind": "Role", "role": "Manager"},
        {"kind": "Document field", "field": "manager"},
        {"kind": "Email", "email": "a@b.c"},
    ]


def test_migration_moves_old_rules(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE grunt_metadata_doc_type (name VARCHAR, definition JSON)")
        )
        conn.execute(
            sa.text("INSERT INTO grunt_metadata_doc_type VALUES ('Notification', :d)"),
            {
                "d": json.dumps(
                    {
                        "name": "Notification",
                        "fields": [
                            {"fieldname": "channel"},
                            {"fieldname": "recipients"},
                            {"fieldname": "event"},
                        ],
                    }
                )
            },
        )
        conn.execute(
            sa.text(
                "CREATE TABLE grunt_notification (name VARCHAR PRIMARY KEY, owner VARCHAR, "
                "event VARCHAR, channel VARCHAR, recipients VARCHAR, "
                "subject_template VARCHAR, message_template TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO grunt_notification VALUES "
                "('r1', 'admin@x', 'after_save', 'both', 'owner, role:Manager', "
                "'{doctype}: {name}', 'Стан {status}')"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # nothing left to move

        columns = {c["name"] for c in sa.inspect(conn).get_columns("grunt_notification")}
        rule = conn.execute(
            sa.text("SELECT subject_template, message_template FROM grunt_notification")
        ).one()
        recipients = conn.execute(
            sa.text(
                "SELECT kind, role, parent_field, idx FROM grunt_notification_recipient "
                "WHERE parent_name = 'r1' ORDER BY idx"
            )
        ).all()
        channels = conn.execute(
            sa.text("SELECT channel FROM grunt_notification_channel ORDER BY idx")
        ).all()
        stored = conn.execute(sa.text("SELECT definition FROM grunt_metadata_doc_type")).scalar()
        definition = json.loads(stored or "{}")

    assert "channel" not in columns and "recipients" not in columns
    assert tuple(rule) == ("{{ doctype }}: {{ doc.name }}", "Стан {{ doc.status }}")
    assert [tuple(r) for r in recipients] == [
        ("Author", None, "recipients", 1),
        ("Role", "Manager", "recipients", 2),
    ]
    assert [c for (c,) in channels] == ["in_app", "web_push", "email"]
    assert [f["fieldname"] for f in definition["fields"]] == ["recipients", "event"]


@pytest.mark.asyncio
async def test_inactive_accounts_are_left_out(ctx, tickets):
    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        await ctx.new_doc(
            "User",
            {
                "email": "gone@grunt.example.com",
                "first_name": "Г",
                "last_name": "Т",
                "is_active": False,
            },
        )
        await ctx.db.insert_one(
            "DocFollow",
            {
                "name": "f-gone",
                "owner": "gone@grunt.example.com",
                "reference_doctype": "NotifTicket",
                "reference_id": "T-1",
                "user": "gone@grunt.example.com",
            },
        )
        rule = await _rule(ctx, recipients=[{"kind": "Followers"}, {"kind": "Author"}])
        await _run(ctx, rule, await _ticket(ctx))
        rule = await _rule(ctx, recipients=[{"kind": "Email", "email": "gone@grunt.example.com"}])
        await _run(ctx, rule, await _ticket(ctx))
        recipients = [r for r, _c, _s in await _deliveries(ctx)]

    # The follow is dropped; an Email row naming the address is kept on purpose.
    assert sorted(recipients) == ["gone@grunt.example.com", OWNER]


def test_downgrade_refuses():
    with pytest.raises(NotImplementedError):
        migration.downgrade()


@pytest.mark.asyncio
async def test_url_for_a_doctype_not_loaded_yet(ctx, tickets, monkeypatch):
    """The worker knows only DocType names until asked - the link still works."""
    from grunt.metadata.registry import doctype_registry
    from grunt.notification.channels import desk_url

    async with ctx.system_context(ctx.db._session(), ctx.get_engine()):
        # As after prefetch_names: the name is known, the definition not loaded.
        monkeypatch.delitem(doctype_registry._doctypes, "NotifTicket", raising=False)
        doctype_registry._known_names.add("NotifTicket")
        doctype_registry._known_index_add("NotifTicket")
        assert (await desk_url("NotifTicket", "T-1") or "").endswith("/NotifTicket/T-1")
