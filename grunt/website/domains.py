"""An app's website on a domain of its own (``web_domains`` in ``grunt.site``).

www pages of an app other than the primary one are mounted at ``/<app>/...``
once per process. On the app's own host the same pages are served from the
root: :func:`domain_path` rewrites ``/datasets`` to ``/opendata/datasets``
before routing, and :func:`grunt.website.generator.app_mount` drops the
prefix from the links the app builds - so one process serves the main site
and every app domain, without a proxy rewriting paths.

What stays where it is on an app domain: the API, the Desk (``/app``, login),
core pages (``/login``, ``/sitemap.xml``), mounted assets and root static
files - unless the app has a page of the same name, which wins.
"""

from starlette.routing import Match

lazy from grunt.startup.website import is_core_path

CATCH_ALL = "/{path:path}"


def _matches(routes: list, path: str, method: str) -> bool:
    """Whether a route other than the website catch-all takes *path*."""
    scope = {"type": "http", "path": path, "root_path": "", "method": method}
    for route in routes:
        if getattr(route, "path", None) == CATCH_ALL:
            continue
        match, _child = route.matches(scope)
        if match is not Match.NONE:
            return True
    return False


def domain_path(path: str, app: str, routes: list, method: str = "GET") -> str | None:
    """The path to route instead of *path* on *app*'s own domain, ``None`` to
    keep it.

    ``/<app>/...`` itself is never rewritten (see :func:`canonical_path`).
    The app's page wins over a core route of the same path; a path nothing
    but the catch-all takes - web view documents, page resolvers, the 404 -
    belongs to the app unless it is a Desk route or a root static file.
    """
    mount = f"/{app}"
    if path == mount or path.startswith(mount + "/"):
        return None
    prefixed = mount if path == "/" else mount + path
    if _matches(routes, prefixed, method):
        return prefixed
    if path != "/" and (_matches(routes, path, method) or is_core_path(path)):
        return None
    return prefixed


def canonical_path(path: str, app: str) -> str | None:
    """``/datasets`` for ``/opendata/datasets`` on the app's domain - the
    address to redirect a prefixed link to; ``None`` when *path* has no prefix."""
    mount = f"/{app}"
    if path == mount:
        return "/"
    if path.startswith(mount + "/"):
        return path[len(mount) :]
    return None


__all__ = ["canonical_path", "domain_path"]
