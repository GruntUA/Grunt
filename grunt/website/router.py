"""
Website page rendering engine — Enhanced routing for Grunt apps.
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
_GRUNT_WWW_TEMPLATES_DIR = Path(__file__).parent / "templates"


class WebsitePage:
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
        return f"<WebsitePage app={self.app!r} url={self.url_pattern!r}>"


class WebsiteRegistry:
    """Collects WebsitePage objects from all installed apps."""

    def __init__(self) -> None:
        self._pages: list[WebsitePage] = []
        # Jinja2 Environment per app name
        self._envs: dict[str, Environment] = {}

    def discover_app(self, app_dir: Path, app_name: str, is_main_app: bool = False) -> list[WebsitePage]:
        """Scan app_dir/www/ for .html files and register pages."""
        www_dir = app_dir / "www"
        if not www_dir.is_dir():
            return []

        loaders: list[FileSystemLoader] = [FileSystemLoader(str(www_dir))]
        if _GRUNT_WWW_TEMPLATES_DIR.is_dir():
            loaders.append(FileSystemLoader(str(_GRUNT_WWW_TEMPLATES_DIR)))

        self._envs[app_name] = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html"]),
            enable_async=True,
        )

        discovered: list[WebsitePage] = []
        for html_file in sorted(www_dir.rglob("*.html")):
            if html_file.name.startswith("_"):
                continue  # skip base/partial templates (_base.html, _header.html …)

            rel_parts = list(html_file.relative_to(www_dir).parts)
            stem = rel_parts[-1][:-5]  # strip ".html"

            if stem == "index":
                rel_parts = rel_parts[:-1]
            else:
                rel_parts[-1] = stem

            # Routing Logic:
            # 1. Main app (grunt) pages are mounted at root: /login, /signup
            # 2. Other apps are mounted with prefix: /hrm/dashboard
            # 3. If a page is named 'index' in a subfolder, it takes the folder name
            
            if is_main_app:
                url_pattern = "/" + "/".join(rel_parts) if rel_parts else "/"
            else:
                url_pattern = "/" + "/".join([app_name] + rel_parts) if rel_parts else f"/{app_name}"

            page = WebsitePage(html_file, www_dir, app_name, url_pattern)
            self._pages.append(page)
            discovered.append(page)
            logger.info("website.page.discovered", app=app_name, url=url_pattern)

        return discovered

    def get_env(self, app_name: str) -> Environment | None:
        return self._envs.get(app_name)

    @property
    def pages(self) -> list[WebsitePage]:
        return list(self._pages)


website_registry = WebsiteRegistry()


async def render_page(
    page: WebsitePage,
    request: Request,
    path_params: dict[str, Any] | None = None,
    session: Any | None = None,
) -> HTMLResponse:
    """Load controller context, render Jinja2 template, return HTMLResponse."""
    from grunt.app import grunt  # noqa: PLC0415
    from grunt.config import settings  # noqa: PLC0415
    
    context: dict[str, Any] = {
        "request": request,
        "path_params": path_params or {},
        "query_params": dict(request.query_params),
        "session": session,
        "title": "",
        "description": "",
        "dev_mode": settings.debug,
    }

    try:
        # Fetch global website settings (Singleton)
        ws = await grunt.get_doc("WebsiteSettings", "WebsiteSettings", session=session)
        context["website_settings"] = ws
    except Exception:
        context["website_settings"] = None

    if page.py_file:
        try:
            spec = importlib.util.spec_from_file_location("_www_controller", page.py_file)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[arg-type]

                # Handle POST logic if present
                if request.method == "POST" and hasattr(mod, "handle_post"):
                    result = mod.handle_post(context)
                    if inspect.isawaitable(result):
                        result = await result
                    # If handle_post returns a response, return it immediately (e.g. redirect)
                    if isinstance(result, HTMLResponse):
                        return result
                    if isinstance(result, dict):
                        context.update(result)

                if hasattr(mod, "get_context"):
                    result = mod.get_context(context)
                    if inspect.isawaitable(result):
                        result = await result
                    if isinstance(result, dict):
                        context.update(result)
        except Exception as e:
            logger.warning("website.controller.error", file=str(page.py_file), error=str(e))

    env = website_registry.get_env(page.app)
    if env is None:
        raise ValueError(f"No Jinja2 environment for app '{page.app}'")

    template_name = context.get("template_name") or page.template_name
    template = env.get_template(template_name)
    html = await template.render_async(**context)
    return HTMLResponse(content=html)


async def render_page_by_route(
    request: Request,
    session: Any,
) -> HTMLResponse | None:
    """Try to render a page by its route, checking both files and database."""
    from grunt.app import grunt  # noqa: PLC0415
    
    path = request.url.path
    # Clean trailing slash for matching
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # 1. Try file-based pages first
    for page in website_registry.pages:
        # Simple match for now (could be improved with regex for path params)
        if page.url_pattern == path:
            return await render_page(page, request, session=session)

    # 2. Try database-based pages (WebPage)
    try:
        pages = await grunt.get_all(
            "WebPage",
            filters={"route": path, "published": 1},
            limit=1,
            session=session
        )
        if pages:
            doc = await grunt.get_doc("WebPage", pages[0]["id"], session=session)
            return await render_db_page(doc, request, session=session)
    except Exception as e:
        logger.warning("website.db_page.error", route=path, error=str(e))

    return None


async def render_db_page(doc: Any, request: Request, session: Any) -> HTMLResponse:
    """Render a dynamic page from the database using a generic template."""
    from grunt.config import settings  # noqa: PLC0415
    from grunt.app import grunt  # noqa: PLC0415

    context: dict[str, Any] = {
        "request": request,
        "doc": doc,
        "title": doc.title,
        "description": doc.meta_description or "",
        "content": doc.content,
        "dev_mode": settings.debug,
    }

    try:
        ws = await grunt.get_doc("WebsiteSettings", "WebsiteSettings", session=session)
        context["website_settings"] = ws
    except Exception:
        context["website_settings"] = None

    # Use main app env for generic templates
    env = website_registry.get_env("grunt")
    if env is None:
        raise ValueError("No Jinja2 environment found")

    try:
        template = env.get_template("web_page.html")
    except Exception:
        # Fallback to a very basic render if no template found
        template = env.from_string("""
            {% extends "_base.html" %}
            {% block content %}
            <div class="container py-5">
                <article>
                    <header class="mb-5">
                        <h1 class="display-4" style="font-family: 'Outfit'; font-weight: 700;">{{ doc.title }}</h1>
                    </header>
                    <div class="cms-content" style="font-size: 1.125rem; line-height: 1.75; color: var(--text-main);">
                        {{ doc.content | safe }}
                    </div>
                </article>
            </div>
            {% endblock %}
        """)

    html = await template.render_async(**context)
    return HTMLResponse(content=html)


def make_website_handler(page: WebsitePage):
    """Return a FastAPI route handler for the given WebsitePage."""
    from grunt.db.session import get_session  # noqa: PLC0415

    async def _handler(
        request: Request,
        session: Any = Depends(get_session),
    ) -> HTMLResponse:
        return await render_page(page, request, dict(request.path_params) or None, session=session)

    safe = page.url_pattern.replace("/", "_").replace("{", "").replace("}", "")
    _handler.__name__ = f"website_{page.app}{safe}"
    return _handler
