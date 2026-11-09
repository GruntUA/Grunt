"""An app's website on its own domain (``web_domains`` in ``grunt.site``):
the host picks the site and the app served at the root."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from grunt.site.manager import SiteManager
from grunt.website.domains import canonical_path, domain_path


def _site(sites_dir: Path, name: str, **config: object) -> None:
    (sites_dir / name).mkdir(parents=True)
    (sites_dir / name / "grunt.site").write_text(json.dumps(config))


def _manager(sites_dir: Path) -> SiteManager:
    manager = SiteManager()
    manager.sites_dir = sites_dir
    return manager


def test_web_domains_from_site_config(tmp_path: Path) -> None:
    _site(
        tmp_path,
        "a.example",
        installed_apps=["grunt", "portal", "data"],
        web_domains={"Data.Example.org": "data", "x.example.org": "missing", "b.example": "data"},
    )
    _site(
        tmp_path,
        "b.example",
        installed_apps=["grunt", "data"],
        web_domains={"data.example.org": "data", "own.example.org": "data"},
    )
    manager = _manager(tmp_path)
    assert manager.get_web_domains() == {
        "data.example.org": ("a.example", "data"),  # first site wins, host lower-cased
        "own.example.org": ("b.example", "data"),
    }  # not installed / a site's own name - skipped
    assert manager.domain_apps("a.example") == {"data": "data.example.org"}
    assert manager.domain_apps("c.example") == {}


def test_web_domains_skip_empty_hosts_and_site_names_in_any_case(tmp_path: Path) -> None:
    _site(tmp_path, "Shop.Example", installed_apps=["grunt"])
    _site(
        tmp_path,
        "a.example",
        installed_apps=["grunt", "data"],
        web_domains={"": "data", "  ": "data", "shop.example": "data", "ok.example": "data"},
    )
    assert _manager(tmp_path).get_web_domains() == {"ok.example": ("a.example", "data")}


def _routes() -> list:
    app = FastAPI()

    async def page() -> str:
        return ""

    for path in ("/data", "/data/datasets", "/data/dataset/{name}", "/data/login", "/login"):
        app.add_api_route(path, page)
    app.add_api_route("/api/v1/x", page, methods=["GET", "POST"])
    app.add_api_route("/{path:path}", page)
    return app.router.routes


@pytest.mark.parametrize(
    ("path", "routed"),
    [
        ("/", "/data"),  # the app's index
        ("/datasets", "/data/datasets"),
        ("/dataset/abc", "/data/dataset/abc"),
        ("/login", "/data/login"),  # the app's page wins over the core one
        ("/news/some-doc", "/data/news/some-doc"),  # web views, resolvers, the 404
        ("/api/v1/x", None),  # the API stays
        ("/app/Item/1", None),  # the Desk stays
        ("/reset-password", None),
        ("/favicon.svg", None),  # a root static file
        ("/data/datasets", None),  # already prefixed - redirected instead
    ],
)
def test_domain_path(path: str, routed: str | None) -> None:
    assert domain_path(path, "data", _routes()) == routed


def test_canonical_path() -> None:
    assert canonical_path("/data", "data") == "/"
    assert canonical_path("/data/datasets", "data") == "/datasets"
    assert canonical_path("/database", "data") is None
    assert canonical_path("/datasets", "data") is None


@pytest.fixture
def domain_app(monkeypatch: pytest.MonkeyPatch):
    """App ``dom`` with one page, served at the root of ``dom.test``."""
    from grunt.apps.loader import _move_before_catch_all
    from grunt.main import app
    from grunt.site.manager import site_manager
    from grunt.website.generator import app_mount

    async def hello(request: Request) -> PlainTextResponse:
        return PlainTextResponse(f"{app_mount('dom')}|{request.url.path}")

    monkeypatch.setattr(
        site_manager, "get_web_domains", lambda: {"dom.test": ("__pytest__", "dom")}
    )
    app.add_api_route("/dom/hello", hello)
    _move_before_catch_all(app)
    route = next(r for r in app.router.routes if getattr(r, "path", None) == "/dom/hello")
    yield
    app.router.routes.remove(route)


@pytest.mark.asyncio
async def test_app_page_at_the_root_of_its_domain(client, domain_app):
    r = await client.get("/hello", headers={"Host": "dom.test"})
    assert r.status_code == 200
    assert r.text == "|/dom/hello"  # links without the prefix

    r = await client.get("/dom/hello?q=1", headers={"Host": "dom.test"})
    assert r.status_code == 301
    assert r.headers["location"] == "/hello?q=1"

    # Elsewhere the app keeps its prefix
    r = await client.get("/dom/hello")
    assert r.status_code == 200
    assert r.text == "/dom|/dom/hello"
    assert (await client.get("/hello")).status_code == 404


@pytest.mark.asyncio
async def test_core_stays_on_an_app_domain(client, domain_app):
    r = await client.get("/app/some/route", headers={"Host": "dom.test", "Accept": "text/html"})
    assert r.status_code == 200
    assert 'id="app"' in r.text
    assert (await client.head("/robots.txt", headers={"Host": "dom.test"})).status_code == 200
    r = await client.get("/no-such-page", headers={"Host": "dom.test", "Accept": "text/html"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sitemap_is_per_host(ctx, monkeypatch):
    from grunt.site.manager import site_manager
    from grunt.website import sitemap
    from grunt.website.host import current_web_app

    async def source():
        return ["/dom/from-source"]

    source.__module__ = "dom.web"
    monkeypatch.setattr(site_manager, "domain_apps", lambda site: {"dom": "dom.test"})
    sitemap.register_sitemap_source(source)
    try:
        assert "/dom/from-source" not in await sitemap.sitemap_entries()
        token = current_web_app.set("dom")
        try:
            entries = await sitemap.sitemap_entries()
        finally:
            current_web_app.reset(token)
    finally:
        sitemap._sitemap_sources.remove(source)
    assert entries == ["/dom/from-source"]
