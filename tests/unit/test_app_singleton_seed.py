"""An app's singleton gets its one row on app sync — filled from field defaults."""

import pytest

from grunt.metadata.doctype import DocType
from grunt.metadata.field import DocField


@pytest.mark.asyncio
async def test_app_singleton_row_seeded_from_defaults(ctx, db_session, engine):
    from grunt.metadata.registry import doctype_registry
    from grunt.startup.app_install import _seed_app_singletons

    dt = DocType(
        name="AcmeSettings",
        label="Acme settings",
        module="acme",
        app="acme",
        is_singleton=True,
        fields=[
            DocField(fieldname="enabled", label="On", fieldtype="Check", default=1),
            DocField(fieldname="term", label="Term", fieldtype="Int", default=30),
            DocField(fieldname="note", label="Note", fieldtype="Text"),
        ],
    )
    await doctype_registry.register(dt, db_session, engine)

    await _seed_app_singletons("acme")
    row = await ctx.get_doc("AcmeSettings")
    assert (bool(row["enabled"]), row["term"], row["note"]) == (True, 30, None)

    # Never touches an existing row.
    await ctx.save_doc("AcmeSettings", "AcmeSettings", {"term": 15})
    await _seed_app_singletons("acme")
    assert await ctx.db.count("AcmeSettings") == 1
    assert (await ctx.get_doc("AcmeSettings"))["term"] == 15
