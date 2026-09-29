"""Production (``debug`` off) wiring: the root web app comes from ``grunt.site``
and the built SPA (``dist/``) is served by the backend itself."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from grunt.site.manager import SiteManager
from grunt.website import spa

if TYPE_CHECKING:
    from pathlib import Path


def _site(sites_dir: Path, name: str, **config: object) -> None:
    (sites_dir / name).mkdir(parents=True)
    (sites_dir / name / "grunt.site").write_text(json.dumps(config))


def _manager(sites_dir: Path) -> SiteManager:
    manager = SiteManager()
    manager.sites_dir = sites_dir
    return manager


def test_primary_web_app_from_site_config(tmp_path: Path) -> None:
    _site(tmp_path, "b.example", installed_apps=["grunt", "portal"], primary_web_app="portal")
    _site(tmp_path, "a.example", installed_apps=["grunt"])
    assert _manager(tmp_path).get_primary_web_app() == "portal"


def test_primary_web_app_must_be_installed(tmp_path: Path) -> None:
    _site(tmp_path, "a.example", installed_apps=["grunt"], primary_web_app="portal")
    assert _manager(tmp_path).get_primary_web_app() is None


def test_primary_web_app_first_site_wins(tmp_path: Path) -> None:
    _site(tmp_path, "a.example", installed_apps=["one"], primary_web_app="one")
    _site(tmp_path, "b.example", installed_apps=["two"], primary_web_app="two")
    assert _manager(tmp_path).get_primary_web_app() == "one"


def test_spa_assets_takes_entry_tags_from_built_index(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text(
        '<head><link href="https://fonts.googleapis.com/css2" rel="stylesheet">\n'
        '<script type="module" crossorigin src="/assets/index-abc.js"></script>\n'
        '<link rel="modulepreload" crossorigin href="/assets/vendor-def.js">\n'
        '<link rel="stylesheet" crossorigin href="/assets/index-ghi.css">\n'
        '<link rel="manifest" href="/manifest.webmanifest"></head>'
    )
    monkeypatch.setattr(spa, "DIST_DIR", tmp_path)
    monkeypatch.setattr(spa, "_cache", None)

    tags = str(spa.spa_assets())
    assert "/assets/index-abc.js" in tags
    assert "/assets/vendor-def.js" in tags
    assert "/assets/index-ghi.css" in tags
    assert "googleapis" not in tags
    assert "manifest" not in tags


def test_static_file_stays_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "app.js").write_text("x")
    (tmp_path / "secret.txt").write_text("s")

    assert spa.static_file(root, "assets/app.js") == (root / "assets" / "app.js").resolve()
    assert spa.static_file(root, "../secret.txt") is None
    assert spa.static_file(root, "assets") is None
    assert spa.static_file(root, "") is None
