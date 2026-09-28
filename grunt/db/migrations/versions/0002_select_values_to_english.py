"""Rename Ukrainian Select option values of core DocTypes to English.

The framework's source language is English; these Select fields used to store
Ukrainian words. Their option values are now English (captions are translated
through the ``translatable`` flag + ``select:<DocType>.<field>`` catalog
entries), so rows saved before this change are rewritten to the new values.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# table -> column -> {old value: new value}
_RENAMES: dict[str, dict[str, dict[str, str]]] = {
    "grunt_email_email_account": {
        "provider": {"Інший провайдер": "Other"},
    },
    "grunt_email_email_message": {
        "direction": {"Вхідний": "Incoming", "Вихідний": "Outgoing"},
        "status": {
            "Отримано": "Received",
            "Надіслано": "Sent",
            "Доставлено": "Delivered",
            "Не доставлено": "Undelivered",
            "Відкладено": "Deferred",
            "У черзі": "Queued",
            "Помилка": "Error",
        },
    },
    "grunt_geo_address": {
        "address_type": {
            "Реєстрації": "Registered",
            "Фактична": "Actual",
            "Поштова": "Postal",
            "Юридична": "Legal",
        },
    },
    "grunt_geo_country": {
        "continent": {
            "Африка": "Africa",
            "Азія": "Asia",
            "Австралія та Океанія": "Australia and Oceania",
            "Антарктида": "Antarctica",
            "Європа": "Europe",
            "Північна Америка": "North America",
            "Південна Америка": "South America",
        },
    },
    "grunt_geo_region": {
        "region_type": {
            "Область": "Oblast",
            "Штат": "State",
            "Провінція": "Province",
            "Земля": "Land",
            "Регіон": "Region",
            "Кантон": "Canton",
            "Департамент": "Department",
            "Інше": "Other",
        },
    },
}


def _apply(mapping_for: dict[str, dict[str, dict[str, str]]]) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    for table, columns in mapping_for.items():
        if table not in tables:
            continue  # DocType not installed on this site
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column, values in columns.items():
            if column not in existing:
                continue
            tbl = sa.table(table, sa.column(column))
            for old, new in values.items():
                conn.execute(
                    sa.update(tbl).where(tbl.c[column] == old).values({column: new})
                )


def upgrade() -> None:
    _apply(_RENAMES)


def downgrade() -> None:
    _apply(
        {
            table: {col: {new: old for old, new in vals.items()} for col, vals in cols.items()}
            for table, cols in _RENAMES.items()
        }
    )
