"""DocType web view: documents of an opted-in DocType are served as public
pages at ``/<web_route>/<route>`` (grunt.website.generator)."""

from __future__ import annotations

import pytest

ARTICLE = {
    "name": "WebArticle",
    "label": "Web Article",
    "module": "core",
    "title_field": "title",
    "has_web_view": True,
    "allow_guest_to_view": True,
    "web_route": "articles",
    "is_published_field": "published",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
        {"fieldname": "route", "label": "Route", "fieldtype": "Text"},
        {"fieldname": "published", "label": "Published", "fieldtype": "Check"},
        {"fieldname": "sec_body", "label": "Story", "fieldtype": "Section"},
        {"fieldname": "body", "label": "Body", "fieldtype": "RichText"},
        {"fieldname": "secret", "label": "Secret", "fieldtype": "Text", "hidden": True},
    ],
    "permissions": [{"role": "System Manager", "read": True, "write": True, "create": True}],
}


async def _article_doctype(ctx, **extra):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**ARTICLE, **extra, "__is_new": True})
    await ctx.db._session().commit()


async def _get(session, path: str) -> str:
    """Render *path* the way the website catch-all does (it opens its own
    site session, which can't see the test database)."""
    from starlette.requests import Request

    from grunt.website.router import render_page_by_route

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("test", 80),
        "root_path": "",
    }
    resp = await render_page_by_route(Request(scope), session)
    return resp.body.decode() if resp is not None else ""


async def _sitemap() -> list[str]:
    from grunt.website.generator import sitemap_urls

    return await sitemap_urls()


async def _article(ctx, title: str, **data) -> dict:
    doc = await ctx.new_doc("WebArticle", {"title": title, **data})
    await ctx.db._session().commit()
    return doc


@pytest.mark.asyncio
async def test_route_filled_from_title_and_kept_unique(ctx):
    await _article_doctype(ctx)
    first = await _article(ctx, "Весняний ярмарок")
    second = await _article(ctx, "Весняний ярмарок")
    custom = await _article(ctx, "Інше", route="own-slug")

    assert first["route"] == "vesnianyi-iarmarok"
    assert second["route"] == "vesnianyi-iarmarok-2"
    assert custom["route"] == "own-slug"


@pytest.mark.asyncio
async def test_published_document_is_served(ctx, db_session):
    await _article_doctype(ctx)
    await _article(
        ctx, "Spring fair", published=1, body="<p>Stalls <b>open</b></p>", secret="classified"
    )

    body = await _get(db_session, "/articles/spring-fair")

    assert "<h1>Spring fair</h1>" in body
    assert "Web Article" in body  # generic layout: DocType label as kicker
    assert "Story" in body  # the DocType's own section structure
    assert "Stalls <b>open</b>" in body  # RichText renders as markup
    assert "classified" not in body  # hidden fields never reach the page
    assert "index, follow" in body


@pytest.mark.asyncio
async def test_unpublished_document_is_not_served(ctx, db_session):
    await _article_doctype(ctx)
    await _article(ctx, "Draft story")

    assert await _get(db_session, "/articles/draft-story") == ""


@pytest.mark.asyncio
async def test_without_guest_access_nothing_is_served(ctx, db_session):
    await _article_doctype(ctx, allow_guest_to_view=False)
    await _article(ctx, "Members only", published=1)

    assert await _get(db_session, "/articles/members-only") == ""


@pytest.mark.asyncio
async def test_noindex_pages_left_out_of_sitemap(ctx, db_session):
    await _article_doctype(ctx, index_web_pages_for_search=False)
    await _article(ctx, "Quiet page", published=1)

    assert "noindex, nofollow" in await _get(db_session, "/articles/quiet-page")
    assert await _sitemap() == []


@pytest.mark.asyncio
async def test_sitemap_lists_published_pages(ctx):
    await _article_doctype(ctx)
    await _article(ctx, "Listed", published=1)
    await _article(ctx, "Hidden draft")

    assert await _sitemap() == ["/articles/listed"]


@pytest.mark.asyncio
async def test_api_response_carries_web_url(ctx, client, auth_headers):
    await _article_doctype(ctx)
    live = await _article(ctx, "Live", published=1)
    draft = await _article(ctx, "Draft")

    live_resp = await client.get(f"/api/v1/docs/WebArticle/{live['name']}", headers=auth_headers)
    draft_resp = await client.get(f"/api/v1/docs/WebArticle/{draft['name']}", headers=auth_headers)

    assert live_resp.json()["data"]["__web_url"] == "/articles/live"
    assert "__web_url" not in draft_resp.json()["data"]


@pytest.mark.asyncio
async def test_name_is_the_route_without_a_route_field(ctx, db_session):
    fields = [f for f in ARTICLE["fields"] if f["fieldname"] != "route"]
    await _article_doctype(ctx, fields=fields, is_published_field=None)
    doc = await _article(ctx, "By name")

    assert "<h1>By name</h1>" in await _get(db_session, f"/articles/{doc['name']}")


@pytest.mark.asyncio
async def test_web_page_and_web_form_report_their_own_urls(ctx, client, auth_headers):
    page = await ctx.new_doc("WebPage", {"title": "About", "route": "/about", "published": 1})
    form = await ctx.new_doc(
        "WebForm",
        {"title": "Feedback", "route": "feedback", "ref_doctype": "User", "is_published": 1},
    )
    draft = await ctx.new_doc("WebPage", {"title": "Soon", "route": "/soon"})
    await ctx.db._session().commit()

    async def url(doctype: str, name: str) -> str | None:
        resp = await client.get(f"/api/v1/docs/{doctype}/{name}", headers=auth_headers)
        return resp.json()["data"].get("__web_url")

    assert await url("WebPage", page["name"]) == "/about"
    assert await url("WebForm", form["name"]) == "/form/feedback"
    assert await url("WebPage", draft["name"]) is None


@pytest.mark.asyncio
async def test_missing_page_uses_controller_not_found_hook(ctx, db_session, monkeypatch):
    from grunt.document.base import Document
    from grunt.document.registry import document_registry

    class WebArticle(Document):
        @staticmethod
        async def get_web_not_found_context(context):
            return {"template_name": "web_view.html", "title": "Nothing here", "tabs": []}

    await _article_doctype(ctx)
    await _article(ctx, "Draft story")

    # Without the hook an unpublished page falls through to the next resolver.
    assert await _get(db_session, "/articles/draft-story") == ""

    monkeypatch.setitem(document_registry._controllers, "WebArticle", WebArticle)
    body = await _get(db_session, "/articles/draft-story")
    assert "<h1>Nothing here</h1>" in body
