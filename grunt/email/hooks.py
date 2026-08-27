"""Framework hooks for the email module.

Registered from ``grunt/main.py`` via ``register_doc_events``.
"""

from __future__ import annotations

from typing import Any

from grunt.email.service import SMTP_PASSWORD_MASK


def _mask(row: Any) -> None:
    if isinstance(row, dict) and row.get("smtp_password"):
        row["smtp_password"] = SMTP_PASSWORD_MASK


async def mask_smtp_password(**kwargs: Any) -> None:
    """Replace stored SMTP passwords with a placeholder on read.

    Fires on ``after_read`` for ``EmailAccount``. Superadmins (and the internal
    SYSTEM_USER used by the queue worker / connection test) keep the real value
    so mail delivery is unaffected; everyone else — including System Managers
    editing the account form — only ever sees ``SMTP_PASSWORD_MASK``.
    """
    user = kwargs.get("user")
    if user is not None and getattr(user, "is_superadmin", False):
        return

    doc = kwargs.get("doc")
    if doc is not None:
        _mask(doc)

    data = kwargs.get("data")
    if isinstance(data, list):
        for row in data:
            _mask(row)
    elif isinstance(data, dict):
        _mask(data)
