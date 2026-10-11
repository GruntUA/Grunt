"""Website catch-all: Desk routes get the SPA shell, anything else a real 404;
pages answer HEAD; sitemap and the page-view rate limit tier."""

from __future__ import annotations

import pytest


def test_spa_paths():
    from grunt.startup.website import _is_spa_path

    for path in ("/", "/app", "/app/letter/IncomingLetter/1", "/login", "/403", "/setup/"):
        assert _is_spa_path(path), path
    for path in ("/wp-login.php", "/news/some-slug", "/application", "/apple"):
        assert not _is_spa_path(path), path


@pytest.mark.asyncio
async def test_unknown_path_is_404_not_spa_shell(client):
    r = await client.get("/no-such-page-anywhere", headers={"Accept": "text/html"})
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_desk_route_gets_spa_shell(client):
    r = await client.get("/app/some/route", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert 'id="app"' in r.text


@pytest.mark.asyncio
async def test_head_is_answered(client):
    assert (await client.head("/robots.txt")).status_code == 200
    assert (await client.head("/app")).status_code == 200


def test_sitemap_skips_pages_that_opt_out(tmp_path):
    from grunt.website.router import WebsitePage

    www = tmp_path / "www"
    www.mkdir()
    (www / "about.html").write_text("about")
    (www / "go.html").write_text("")
    (www / "go.py").write_text("sitemap = False\n")
    (www / "item.html").write_text("")

    about = WebsitePage(www / "about.html", www, "x", "/x/about")
    go = WebsitePage(www / "go.html", www, "x", "/x/go")
    item = WebsitePage(www / "item.html", www, "x", "/x/item/{name}")
    assert about.in_sitemap
    assert not go.in_sitemap
    assert not item.in_sitemap  # dynamic routes come from website_sitemap sources


def test_controller_is_cached_until_the_file_changes(tmp_path):
    import os

    from grunt.website.router import WebsitePage

    (tmp_path / "p.html").write_text("")
    py = tmp_path / "p.py"
    py.write_text("VALUE = 1\n")
    page = WebsitePage(tmp_path / "p.html", tmp_path, "x", "/x/p")

    first = page.controller()
    assert first is not None and first.VALUE == 1
    assert page.controller() is first

    py.write_text("VALUE = 2\n")
    stat = py.stat()
    os.utime(py, (stat.st_atime, stat.st_mtime + 5))
    second = page.controller()
    assert second is not None and second is not first and second.VALUE == 2


@pytest.mark.asyncio
async def test_sitemap_lists_source_urls(ctx):
    from grunt.website import router

    async def source():
        return ["/x/from-source", ("/x/dated", "2026-10-01T10:00:00")]

    router.register_sitemap_source(source)
    try:
        entries = await router.sitemap_entries()
    finally:
        router._sitemap_sources.remove(source)
    body = router.render_sitemap("http://test", [*entries, "/x/from-source"])
    assert body.count("<loc>http://test/x/from-source</loc>") == 1
    assert "<loc>http://test/x/dated</loc><lastmod>2026-10-01</lastmod>" in body
    assert "/login<" not in body


def test_page_views_have_their_own_rate_limit_tier():
    from grunt.middleware.rate_limit import _is_page_view, _too_many_requests

    assert _is_page_view("/news/slug", "GET")
    assert _is_page_view("/", "HEAD")
    assert not _is_page_view("/api/v1/method/x", "GET")
    assert not _is_page_view("/form/contact", "POST")

    page = _too_many_requests("/news", 10, {})
    api = _too_many_requests("/api/v1/x", 10, {})
    assert page.status_code == api.status_code == 429
    assert page.headers["content-type"].startswith("text/html")
    assert api.headers["content-type"].startswith("application/json")
    assert page.headers["retry-after"] == "10"
