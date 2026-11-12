"""``Notification``: recipients and channels become tables, templates Jinja.

* ``recipients`` (a comma-separated string: ``owner``, ``role:X``,
  ``{field:x}``, emails) -> ``NotificationRecipient`` rows;
* ``channel`` (``system`` / ``email`` / ``both``) -> ``NotificationChannel``
  rows (``in_app`` + ``web_push`` / ``email`` / all three);
* ``subject_template`` / ``message_template``: ``{field}`` -> ``{{ doc.field }}``
  (``{doctype}``, ``{event}`` stay variables, ``{name}``/``{id}`` -> ``{{ doc.name }}``).

The child tables are created here from the bundled JSON when there are rules
to move (``grunt migrate``'s DocType sync runs after Alembic and finds them in
place); the old columns are dropped, and ``channel`` leaves the stored
definition (a stored field the JSON lacks would stay as a customisation).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-12
"""

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_META = "grunt_metadata_doc_type"
_RULES = "grunt_notification"
_DOCTYPES = Path(__file__).resolve().parents[3] / "notification" / "doctypes"

_CHANNELS = {
    "system": ("in_app", "web_push"),
    "email": ("email",),
    "both": ("in_app", "web_push", "email"),
}
_PLACEHOLDER = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")
_VARIABLES = {"doctype": "doctype", "event": "event", "name": "doc.name", "id": "doc.name"}


def to_jinja(template: str | None) -> str | None:
    """``"{doctype}: {name} ({status})"`` ->
    ``"{{ doctype }}: {{ doc.name }} ({{ doc.status }})"``."""
    if not template:
        return template
    return _PLACEHOLDER.sub(
        lambda m: "{{ " + _VARIABLES.get(m.group(1), f"doc.{m.group(1)}") + " }}", template
    )


def recipient_rows(spec: str | None) -> list[dict[str, str]]:
    """The old comma-separated recipients -> ``NotificationRecipient`` values."""
    rows: list[dict[str, str]] = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if part == "owner":
            rows.append({"kind": "Author"})
        elif part.startswith("role:"):
            rows.append({"kind": "Role", "role": part[5:].strip()})
        elif part.startswith("{field:") and part.endswith("}"):
            rows.append({"kind": "Document field", "field": part[7:-1].strip()})
        elif "@" in part:
            rows.append({"kind": "Email", "email": part})
    return rows


def _child_table(name: str) -> sa.Table:
    from grunt.metadata.compiler import compile_doctype_to_table
    from grunt.metadata.doctype import DocType

    data = json.loads((_DOCTYPES / name / f"{name}.json").read_text(encoding="utf-8"))
    return compile_doctype_to_table(DocType.model_validate({**data, "app": "grunt"}))


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _RULES not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(_RULES)}
    if "channel" not in columns and "recipients" not in columns:
        return  # already moved

    rules = sa.table(
        _RULES,
        sa.column("name"),
        sa.column("owner"),
        sa.column("channel"),
        sa.column("recipients"),
        sa.column("subject_template"),
        sa.column("message_template"),
    )
    rows = conn.execute(sa.select(rules)).mappings().all()

    if rows:
        recipient_table = _child_table("NotificationRecipient")
        channel_table = _child_table("NotificationChannel")
        recipient_table.create(conn, checkfirst=True)
        channel_table.create(conn, checkfirst=True)
        now = datetime.now(UTC)

        def child(parent: str, field: str, idx: int, owner: str) -> dict:
            return {
                "name": uuid.uuid4().hex[:10],
                "owner": owner,
                "created_at": now,
                "modified_at": now,
                "modified_by": owner,
                "parent_name": parent,
                "parent_doctype": "Notification",
                "parent_field": field,
                "idx": idx,
            }

        for rule in rows:
            owner = rule["owner"] or "system"
            for idx, values in enumerate(recipient_rows(rule["recipients"]), start=1):
                conn.execute(
                    recipient_table.insert().values(
                        **child(rule["name"], "recipients", idx, owner), **values
                    )
                )
            channels = _CHANNELS.get(rule["channel"] or "system", _CHANNELS["system"])
            for idx, channel in enumerate(channels, start=1):
                conn.execute(
                    channel_table.insert().values(
                        **child(rule["name"], "channels", idx, owner), channel=channel
                    )
                )
            conn.execute(
                sa.update(rules)
                .where(rules.c.name == rule["name"])
                .values(
                    subject_template=to_jinja(rule["subject_template"]),
                    message_template=to_jinja(rule["message_template"]),
                )
            )

    for column in ("channel", "recipients"):
        if column in columns:
            op.drop_column(_RULES, column)

    if _META in inspector.get_table_names():
        meta = sa.table(_META, sa.column("name"), sa.column("definition", sa.JSON()))
        stored = sa.select(meta.c.definition).where(meta.c.name == "Notification")
        raw = conn.execute(stored).scalar()
        if raw:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            data["fields"] = [
                f for f in data.get("fields") or [] if f.get("fieldname") != "channel"
            ]
            conn.execute(
                sa.update(meta).where(meta.c.name == "Notification").values(definition=data)
            )


def downgrade() -> None:
    # Not reversible - restore the backup taken before the upgrade (grunt db restore).
    raise NotImplementedError("revision 0023 cannot be downgraded: restore a backup")
