"""
www page rendering engine — Frappe-inspired public web pages for Grunt apps.

Apps place files in their www/ directory:
  www/index.html          → /
  www/about.html          → /about
  www/blog/index.html     → /blog
  www/blog/{slug}.html    → /blog/{slug}  (dynamic segment)

Alongside each .html an optional .py controller can define:
    def get_context(context: dict) -> dict | None:
        context["title"] = "My Page"
        return context

Static assets go in public/:
    public/css/style.css  → /assets/{app}/css/style.css
    public/js/app.js      → /assets/{app}/js/app.js
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

logger = structlog.get_logger()

# Grunt-level base templates directory (apps can extend _base.html from here)
_GRUNT_WWW_DIR = Path(__file__).parent / "www_templates"


class WwwPage:
    """A single public web page discovered from an app's www/ directory."""

    def __init__(self, html_file: Path, www_dir: Path, app: str, url_pattern: str) -> None:
        self.html_file = html_file
        self.www_dir = www_dir
        self.app = app
        # FastAPI-style pattern, e.g. "/blog/{slug}"
        self.url_pattern = url_pattern

    @property
    def template_name(self) -> str:
        return str(self.html_file.relative_to(self.www_dir))

    @property
    def py_file(self) -> Path | None:
        f = self.html_file.with_suffix(".py")
        return f if f.exists() else None

    def __repr__(self) -> str:
        return f"<WwwPage app={self.app!r} url={self.url_pattern!r}>"


class WwwPageRegistry:
    """Collects WwwPage objects from all installed apps."""

    def __init__(self) -> None:
        self._pages: list[WwwPage] = []
        # Jinja2 Environment per app name
        self._envs: dict[str, Environment] = {}

    def discover_app(self, app_dir: Path, app_name: str) -> list[WwwPage]:
        """Scan app_dir/www/ for .html files and register pages."""
        www_dir = app_dir / "www"
        if not www_dir.is_dir():
            return []

        loaders: list[FileSystemLoader] = [FileSystemLoader(str(www_dir))]
        if _GRUNT_WWW_DIR.is_dir():
            loaders.append(FileSystemLoader(str(_GRUNT_WWW_DIR)))

        self._envs[app_name] = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html"]),
            enable_async=True,
        )

        discovered: list[WwwPage] = []
        for html_file in sorted(www_dir.rglob("*.html")):
            if html_file.name.startswith("_"):
                continue  # skip base/partial templates (_base.html, _header.html …)

            rel_parts = list(html_file.relative_to(www_dir).parts)
            stem = rel_parts[-1][:-5]  # strip ".html"

            if stem == "index":
                rel_parts = rel_parts[:-1]
            else:
                rel_parts[-1] = stem

            # Prefix with app name: hrm/www/index.html → /hrm
            # hrm/www/departments.html → /hrm/departments
            url_pattern = "/" + "/".join([app_name] + rel_parts) if rel_parts else f"/{app_name}"

            page = WwwPage(html_file, www_dir, app_name, url_pattern)
            self._pages.append(page)
            discovered.append(page)
            logger.info("www.page.discovered", app=app_name, url=url_pattern)

        return discovered

    def get_env(self, app_name: str) -> Environment | None:
        return self._envs.get(app_name)

    @property
    def pages(self) -> list[WwwPage]:
        return list(self._pages)


www_registry = WwwPageRegistry()


async def render_page(
    page: WwwPage,
    request: Request,
    path_params: dict[str, Any] | None = None,
    session: Any | None = None,
) -> HTMLResponse:
    """Load controller context, render Jinja2 template, return HTMLResponse."""
    context: dict[str, Any] = {
        "request": request,
        "path_params": path_params or {},
        "query_params": dict(request.query_params),
        "session": session,
        "title": "",
        "description": "",
    }

    if page.py_file:
        try:
            spec = importlib.util.spec_from_file_location("_www_controller", page.py_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[arg-type]
                if hasattr(mod, "get_context"):
                    result = mod.get_context(context)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, dict):
                        context.update(result)
        except Exception as e:
            logger.warning("www.controller.error", file=str(page.py_file), error=str(e))

    env = www_registry.get_env(page.app)
    if env is None:
        raise ValueError(f"No Jinja2 environment for app '{page.app}'")

    template = env.get_template(page.template_name)
    html = await template.render_async(**context)
    return HTMLResponse(content=html)


def make_www_handler(page: WwwPage):
    """Return a FastAPI route handler for the given WwwPage."""
    from grunt.db.session import get_session

    async def _handler(
        request: Request,
        session: Any = Depends(get_session),
    ) -> HTMLResponse:
        return await render_page(page, request, dict(request.path_params) or None, session=session)

    safe = page.url_pattern.replace("/", "_").replace("{", "").replace("}", "")
    _handler.__name__ = f"www_{page.app}{safe}"
    return _handler
