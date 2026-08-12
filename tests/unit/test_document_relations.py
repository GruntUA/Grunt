"""Tests for grunt.document.relations."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_save_child_tables_propagates_child_doctype_lookup_failure():
    """Regression: persisting child rows is a required step, not best-effort.

    _save_child_tables used to catch any exception, log it, and return as if
    nothing happened — so a broken/missing child DocType silently dropped
    child-table data while create_document/update_document still reported
    success to the caller. It must now propagate so the write pipeline's
    IntegrityError/transaction handling sees the failure.
    """
    from grunt.document.relations import _save_child_tables
    from grunt.metadata.doctype import DocType
    from grunt.metadata.field import DocField

    dt = DocType(
        name="Parent",
        label="Parent",
        module="core",
        fields=[
            DocField(fieldname="items", label="Items", fieldtype="Table", options="MissingChild")
        ],
    )

    session = MagicMock()
    session.execute = AsyncMock()

    user = MagicMock()
    user.email = "system@grunt.local"

    with (
        patch(
            "grunt.document.relations.doctype_registry.get",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await _save_child_tables(
            session, dt, "parent-1", {"items": [{"title": "x"}]}, user, datetime.now(UTC)
        )
