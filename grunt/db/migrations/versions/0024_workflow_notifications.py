"""Workflow transitions notify through ``Notification`` rules.

``WorkflowTransition.notify`` (``owner`` / ``previous`` / ``next``) and
``notify_email`` become ``on_transition`` rules: one per workflow and
combination of recipients, limited to its transitions' actions
(``workflow_actions``) - by email when any of those transitions mailed (a rule
filters by action, so one action can't be mailed on one transition and not on
another). Recipients: ``owner`` -> Author, ``previous``
-> Previous actor, ``next`` -> Next actors; channels: in the system + browser
push (+ email). The text is what the engine used to compose.

A rule is named ``"<DocType> · <action> / <action>"`` - an app shipping the
same notification as a standard record names it so too, and applying the
record then updates this rule instead of adding a second one.

The child tables are created from the bundled JSON if missing (a site that
had no rules before 0023); ``workflow_actions`` is added when the DocType sync
hasn't run yet. ``notify`` / ``notify_email`` are dropped (column and stored
field).

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-12
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_RULES = "grunt_notification"
_WORKFLOWS = "grunt_metadata_workflow"
_TRANSITIONS = "grunt_metadata_workflow_transition"
_DOCTYPES = Path(__file__).resolve().parents[3] / "notification" / "doctypes"

_KINDS = {"owner": "Author", "previous": "Previous actor", "next": "Next actors"}
SUBJECT = "{{ action }}: {{ title }}"
MESSAGE = (
    "{{ _('%(user)s: “%(action)s” — %(from)s → %(to)s') % {'user': actor, 'action': action, "
    "'from': from_label, 'to': to_label} }}"
    "{% if comment %}\n\n{{ _('Comment:') }}\n{{ comment }}{% endif %}"
    "{% if url %}\n\n{{ url }}{% endif %}"
)


def rule_name(doctype: str, actions: list[str]) -> str:
    return f"{doctype} · {' / '.join(actions)}"


def _child_table(name: str) -> sa.Table:
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.doctype import DocType

    data = json.loads((_DOCTYPES / name / f"{name}.json").read_text(encoding="utf-8"))
    return compile_doctype_to_table(DocType.model_validate({**data, "app": "grunt"}))


def _tokens(raw: str | None) -> tuple[str, ...]:
    return tuple(sorted({t.strip() for t in (raw or "").split(",") if t.strip() in _KINDS}))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if _TRANSITIONS not in tables:
        return
    columns = {c["name"] for c in inspector.get_columns(_TRANSITIONS)}
    if "notify" not in columns:
        return  # already moved

    t = sa.table(
        _TRANSITIONS,
        sa.column("parent_name"),
        sa.column("idx"),
        sa.column("action"),
        sa.column("notify"),
        sa.column("notify_email"),
    )
    w = sa.table(_WORKFLOWS, sa.column("name"), sa.column("document_type"))
    doctype_of = dict(conn.execute(sa.select(w.c.name, w.c.document_type)).all())
    rows = conn.execute(
        sa.select(t.c.parent_name, t.c.action, t.c.notify, t.c.notify_email).order_by(
            t.c.parent_name, t.c.idx
        )
    ).all()

    # (workflow, recipients) -> actions in transition order; mailed or not
    groups: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    mailed: dict[tuple[str, tuple[str, ...]], bool] = {}
    for parent, action, notify, email in rows:
        tokens = _tokens(notify)
        if not tokens or not action:
            continue
        actions = groups.setdefault((parent, tokens), [])
        if action not in actions:
            actions.append(action)
        mailed[(parent, tokens)] = mailed.get((parent, tokens), False) or bool(email)

    if groups and _RULES in tables:
        rule_columns = {c["name"] for c in inspector.get_columns(_RULES)}
        if "workflow_actions" not in rule_columns:
            op.add_column(_RULES, sa.Column("workflow_actions", sa.Text()))
            rule_columns.add("workflow_actions")
        recipient_table = _child_table("NotificationRecipient")
        channel_table = _child_table("NotificationChannel")
        recipient_table.create(conn, checkfirst=True)
        channel_table.create(conn, checkfirst=True)
        rules = sa.table(_RULES, *(sa.column(c) for c in rule_columns))
        now = datetime.now(UTC)
        system = {
            "owner": "system",
            "created_at": now,
            "modified_at": now,
            "modified_by": "system",
        }

        for (parent, tokens), actions in groups.items():
            email = mailed[(parent, tokens)]
            doctype = doctype_of.get(parent) or parent
            name = rule_name(doctype, actions)
            if conn.execute(sa.select(rules.c.name).where(rules.c.name == name)).first():
                continue
            values = {
                "name": name,
                **system,
                "ref_doctype": doctype,
                "event": "on_transition",
                "workflow_actions": "\n".join(actions),
                "subject_template": SUBJECT,
                "message_template": MESSAGE,
                "is_enabled": True,
                "is_standard": False,
            }
            conn.execute(
                rules.insert().values({k: v for k, v in values.items() if k in rule_columns})
            )

            def child(field: str, idx: int, name: str = name) -> dict:
                return {
                    "name": uuid.uuid4().hex[:10],
                    **system,
                    "parent_name": name,
                    "parent_doctype": "Notification",
                    "parent_field": field,
                    "idx": idx,
                }

            for idx, token in enumerate(tokens, start=1):
                conn.execute(
                    recipient_table.insert().values(**child("recipients", idx), kind=_KINDS[token])
                )
            channels = ["in_app", "web_push"] + (["email"] if email else [])
            for idx, channel in enumerate(channels, start=1):
                conn.execute(
                    channel_table.insert().values(**child("channels", idx), channel=channel)
                )

    for column in ("notify", "notify_email"):
        if column in columns:
            op.drop_column(_TRANSITIONS, column)

    if _META in tables:
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        stored = sa.select(meta.c.definition).where(meta.c.name == "WorkflowTransition")
        raw = conn.execute(stored).scalar()
        if raw:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            data["fields"] = [
                f
                for f in data.get("fields") or []
                if f.get("fieldname") not in ("notify", "notify_email")
            ]
            conn.execute(
                sa.update(meta).where(meta.c.name == "WorkflowTransition").values(definition=data)
            )


def downgrade() -> None:
    # Not reversible - restore the backup taken before the upgrade (grunt db restore).
    raise NotImplementedError("revision 0024 cannot be downgraded: restore a backup")
