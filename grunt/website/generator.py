"""Web view — documents of a DocType served as public pages.

A DocType opts in with ``has_web_view`` + ``allow_guest_to_view`` and a
``web_route`` prefix. A document's page lives at
``<app mount>/<web_route>/<doc route>``:

* the app mount follows the www/ rule — ``""`` for the core and for the
  primary web app, ``/<app>`` for every other app;
* ``<doc route>`` is the document's ``route`` field when the DocType has one
  (filled from the title on save, see :func:`fill_route`), else its name.

``is_published_field`` (a Check field) gates which documents have a page.

Rendering: ``<doctype dir>/templates/<Name>.html`` when the DocType ships one
(resolved in its app's www/ environment, so it can extend the app's
``_base.html``), else the generic ``web_view.html`` layout. The controller may
add to the template context with ``async def get_web_context(self, context)``.

A page served some other way (``WebPage``, ``WebForm``) reports its URL with a
controller ``@staticmethod get_web_url(doc) -> str | None`` instead.

Pages without ``allow_guest_to_view`` are never served: the site has no login
cookie, so a signed-in reader can't be told apart from a guest.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote

from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from sqlalchemy import select

from grunt.log import log
from grunt.utils.slug import slugify

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import Request
    from fastapi.responses import HTMLResponse

WEB_URL_KEY = "__web_url"
ROUTE_FIELD = "route"

# Shown on the page itself (heading/cover) or pure web plumbing — left out of
# the generic field layout.
_TECHNICAL_FIELDS = {ROUTE_FIELD}

_template_envs: dict[Path, Environment] = {}


# ── URLs ─────────────────────────────────────────────────────────────────


def _has_field(dt: Any, fieldname: str) -> bool:
    return any(f.fieldname == fieldname for f in dt.fields)


def is_public(dt: Any) -> bool:
    """Whether *dt*'s documents are served as pages at all."""
    return bool(dt.has_web_view and dt.allow_guest_to_view and (dt.web_route or "").strip("/"))


def route_prefix(dt: Any) -> str:
    """``/news`` or ``/<app>/news`` — the URL every page of *dt* starts with."""
    from grunt.apps.loader import CORE_APP, primary_web_app

    app = dt.app
    mount = "" if not app or app in (CORE_APP, primary_web_app()) else f"/{app}"
    return f"{mount}/{dt.web_route.strip('/')}"


def is_published(dt: Any, doc: dict[str, Any]) -> bool:
    field = dt.is_published_field
    return not field or str(doc.get(field) or 0) not in ("0", "False", "false")


def doc_route(dt: Any, doc: dict[str, Any]) -> str:
    return str((_has_field(dt, ROUTE_FIELD) and doc.get(ROUTE_FIELD)) or doc.get("name") or "")


def web_url(dt: Any, doc: dict[str, Any]) -> str | None:
    """The public URL of *doc*, or ``None`` while it has no page."""
    if not is_public(dt) or not is_published(dt, doc):
        return None
    route = doc_route(dt, doc)
    return f"{route_prefix(dt)}/{quote(route)}" if route else None


async def with_web_url(doctype: str, doc: Any) -> Any:
    """*doc* (an API response dict) with ``__web_url`` added when it has a page."""
    from grunt.app import grunt
    from grunt.document.registry import document_registry

    if not isinstance(doc, dict):
        return doc
    custom = getattr(document_registry.get(doctype), "get_web_url", None)
    if custom is not None:
        url = custom(doc)
    else:
        dt = await grunt.get_meta(doctype)
        url = web_url(dt, doc) if dt is not None else None
    if url:
        doc[WEB_URL_KEY] = url
    return doc


# ── Route on save ────────────────────────────────────────────────────────


async def fill_route(dt: Any, row: dict[str, Any], session: Any) -> None:
    """Give a web-view document an empty ``route`` a unique slug of its title."""
    if not dt.has_web_view or not _has_field(dt, ROUTE_FIELD) or row.get(ROUTE_FIELD):
        return
    title_field = dt.title_field or "name"
    base = slugify(str(row.get(title_field) or row.get("name") or ""))

    table = dt.table
    candidate, suffix = base, 2
    while True:
        taken = await session.scalar(
            select(table.c.name)
            .where(table.c[ROUTE_FIELD] == candidate, table.c.name != row.get("name"))
            .limit(1)
        )
        if taken is None:
            row[ROUTE_FIELD] = candidate
            return
        candidate, suffix = f"{base}-{suffix}", suffix + 1


# ── Serving ──────────────────────────────────────────────────────────────


async def _find_page(path: str) -> tuple[Any, str | None] | None:
    """``(DocType, document name)`` for a page *path*. The name is ``None`` when
    *path* is under a web view DocType's prefix but no published document is
    there; ``None`` overall when no DocType claims the path."""
    from grunt.app import grunt
    from grunt.metadata.registry import doctype_registry

    claimed = None
    for dt in await doctype_registry.list_all():
        if not is_public(dt):
            continue
        prefix = route_prefix(dt) + "/"
        if not path.startswith(prefix) or len(path) == len(prefix):
            continue
        route = unquote(path[len(prefix) :])
        key = ROUTE_FIELD if _has_field(dt, ROUTE_FIELD) else "name"
        filters: dict[str, Any] = {key: route}
        if dt.is_published_field:
            filters[dt.is_published_field] = 1
        rows = await grunt.db.get_all(dt.name, filters=filters, fields=["name"], limit=1)
        if rows:
            return dt, rows[0]["name"]
        claimed = claimed or dt
    return (claimed, None) if claimed else None


def _template_env(app: str | None, template_dir: Path) -> Environment | None:
    """The app's www/ env, searching *template_dir* first."""
    from grunt.website.router import website_registry

    env = _template_envs.get(template_dir)
    if env is None:
        base = website_registry.get_env(app or "grunt") or website_registry.get_env("grunt")
        if base is None:
            return None
        env = base.overlay(loader=ChoiceLoader([FileSystemLoader(str(template_dir)), base.loader]))
        _template_envs[template_dir] = env
    return env


async def render_doc_page(request: Request, session: Any) -> HTMLResponse | None:
    """Render the web view page at ``request.url.path``; ``None`` if there is none.

    A path under a DocType's prefix with no published document behind it is
    rendered by the controller's optional
    ``@staticmethod async get_web_not_found_context(context)`` (e.g. a styled
    404 in the app's own layout); without that hook it falls through like any
    unknown path.
    """
    from grunt.app import grunt
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.config import settings
    from grunt.document.registry import document_registry
    from grunt.website.doc_layout import build_tabs

    path = request.url.path.rstrip("/")
    async with grunt.context(session, user=SYSTEM_USER):
        found = await _find_page(path)
        if found is None:
            return None
        dt, name = found
        controller_cls = document_registry.get(dt.name)

        context: dict[str, Any] = {
            "request": request,
            "path_params": {},
            "query_params": dict(request.query_params),
            "session": session,
            "dev_mode": settings.debug,
            "doctype": dt,
            "description": "",
            "noindex": not dt.index_web_pages_for_search,
        }
        try:
            context["website_settings"] = await grunt.get_doc("WebsiteSettings")
        except Exception:
            context["website_settings"] = None

        if name is None:
            hook = getattr(controller_cls, "get_web_not_found_context", None)
            if hook is None:
                return None
            context.update(status_code=404, title="", doc=None)
            await _apply(hook(context), context)
        else:
            doc = await grunt.get_doc(dt.name, name)
            title_field = dt.title_field or "name"
            context.update(
                doc=doc,
                title=str(doc.get(title_field) or name),
                image=doc.get(dt.image_field) if dt.image_field else None,
                tabs=build_tabs(
                    list(dt.fields),
                    doc,
                    skip={
                        *_TECHNICAL_FIELDS,
                        title_field,
                        dt.image_field or "",
                        dt.is_published_field or "",
                    },
                ),
            )
            controller = controller_cls(dt.name, doc, SYSTEM_USER, session)
            hook = getattr(controller_cls, "get_web_context", None)
            if hook is not None:
                await _apply(hook(controller, context), context)

    return await _render(dt, context)


async def _apply(result: Any, context: dict[str, Any]) -> None:
    """Merge a (possibly awaitable) hook result into *context*."""
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, dict):
        context.update(result)


async def _render(dt: Any, context: dict[str, Any]) -> HTMLResponse | None:
    from fastapi.responses import HTMLResponse

    from grunt.document.registry import document_registry
    from grunt.website.router import website_registry

    dt_dir = document_registry.doctype_dir(dt.name)
    template_dir = dt_dir / "templates" if dt_dir else None
    custom = template_dir is not None and (template_dir / f"{dt.name}.html").is_file()
    env = (
        _template_env(dt.app, template_dir)
        if custom and template_dir
        else website_registry.get_env("grunt")
    )
    if env is None:
        log.warning("website.web_view.no_env", doctype=dt.name)
        return None
    template_name = context.get("template_name") or (
        f"{dt.name}.html" if custom else "web_view.html"
    )
    html = await env.get_template(template_name).render_async(**context)
    return HTMLResponse(content=html, status_code=context.get("status_code") or 200)


async def sitemap_urls() -> list[str]:
    """Paths of every indexed web view page (caller holds a grunt context)."""
    from grunt.app import grunt
    from grunt.metadata.registry import doctype_registry

    urls: list[str] = []
    for dt in await doctype_registry.list_all():
        if not is_public(dt) or not dt.index_web_pages_for_search:
            continue
        filters = {dt.is_published_field: 1} if dt.is_published_field else None
        extra = (ROUTE_FIELD, dt.is_published_field)
        fields = ["name", *[f for f in extra if f and _has_field(dt, f)]]
        rows = await grunt.db.get_all(dt.name, filters=filters, fields=fields, limit=None)
        urls.extend(url for row in rows if (url := web_url(dt, row)))
    return urls
