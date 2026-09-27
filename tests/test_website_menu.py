"""Site menus as WebsiteMenuItem trees (grunt.website.menu)."""

from __future__ import annotations

import pytest

from grunt.website import menu as site_menu


@pytest.fixture(autouse=True)
def _fresh_cache():
    site_menu.invalidate()
    yield
    site_menu.invalidate()


async def _item(ctx, **data) -> str:
    doc = await ctx.new_doc("WebsiteMenuItem", {"menu": "main", **data})
    return doc["name"]


@pytest.mark.asyncio
async def test_menu_tree_is_ordered_and_hides_disabled_subtrees(ctx):
    about = await _item(ctx, label="About", sequence=2)
    news = await _item(ctx, label="News", url="/news", sequence=1)
    # A child follows its parent's menu, whatever it was created with.
    await _item(ctx, label="Archive", url="/news/archive", parent_menu_item=news, menu="top")
    hidden = await _item(ctx, label="Hidden", parent_menu_item=about, enabled=0)
    await _item(ctx, label="Under hidden", url="/x", parent_menu_item=hidden)
    await ctx.db._session().commit()

    tree = await site_menu.get_menu("main")

    assert [n["label"] for n in tree] == ["News", "About"]
    assert tree[0]["url"] == "/news"
    assert [c["label"] for c in tree[0]["children"]] == ["Archive"]
    assert tree[1]["url"] is None  # a heading
    assert tree[1]["children"] == []  # disabled item hides its whole subtree
    assert await site_menu.get_menu("top") == []


@pytest.mark.asyncio
async def test_menu_item_links_a_document_page(ctx):
    from tests.test_web_view import _article_doctype

    await _article_doctype(ctx)
    live = await ctx.new_doc("WebArticle", {"title": "Hello world", "published": 1})
    draft = await ctx.new_doc("WebArticle", {"title": "Draft", "published": 0})
    await _item(ctx, label="Hello", link_doctype="WebArticle", link_name=live["name"])
    await _item(ctx, label="Draft", link_doctype="WebArticle", link_name=draft["name"])
    await ctx.db._session().commit()

    urls = {n["label"]: n["url"] for n in await site_menu.get_menu("main")}

    assert urls["Hello"] == f"/articles/{live['route']}"
    assert urls["Draft"] is None  # no public page yet → plain heading, not a dead link


@pytest.mark.asyncio
async def test_saving_an_item_invalidates_the_cached_menu(ctx):
    await _item(ctx, label="First")
    await ctx.db._session().commit()
    assert [n["label"] for n in await site_menu.get_menu("main")] == ["First"]

    await _item(ctx, label="Second", sequence=5)
    await ctx.db._session().commit()
    assert [n["label"] for n in await site_menu.get_menu("main")] == ["First", "Second"]
