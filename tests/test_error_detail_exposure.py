"""Exception text reaches a client only where it is the client's own input.

CodeQL py/stack-trace-exposure: the print preview shows the author's Jinja
error (escaped), but any other failure - and the readiness probe - answers
with a generic text, the details going to the log.
"""

import pytest

from tests.support import make_user

LEDGER = {
    "name": "ExpLedger",
    "label": "Exp Ledger",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "Clerk", "actions": ["read", "print"]}],
}


@pytest.fixture
async def ledger(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**LEDGER, "__is_new": True})
    name = (await ctx.new_doc("ExpLedger", {"title": "Q3"}))["name"]
    await ctx.db._session().commit()
    return name


async def _preview(template, ledger, db_session, engine):
    import grunt
    from grunt.api.v1.document.export import preview

    user = make_user("clerk@example.com", roles=["Clerk"])
    async with grunt.context(db_session, engine, user):
        response = await preview("ExpLedger", template, ledger)
    return response.body.decode()


@pytest.mark.asyncio
async def test_preview_shows_the_template_error_escaped(ledger, db_session, engine):
    body = await _preview("{% if %}<b>", ledger, db_session, engine)
    assert "TemplateSyntaxError" in body
    assert "<b>" not in body


@pytest.mark.asyncio
async def test_preview_hides_other_exception_text(ledger, db_session, engine):
    body = await _preview("{{ doc.title + 1 }}", ledger, db_session, engine)
    assert "TypeError" in body
    assert "concatenate" not in body  # str(exc) stays in the log


@pytest.mark.asyncio
async def test_readiness_hides_exception_text(monkeypatch):
    from grunt.api.v1 import health
    from grunt.site.manager import site_manager

    def boom(*_a, **_k):
        raise RuntimeError("postgresql://admin:secret@db/site")

    monkeypatch.setattr(site_manager, "get_active_site", boom)
    result = await health.readiness()
    assert result["data"]["checks"]["db"] == "error"
    assert "secret" not in repr(result)
