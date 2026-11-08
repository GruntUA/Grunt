"""The app served at the root of the request's host - a leaf module (no grunt
imports), so the site middleware and the website modules share it freely."""

from contextvars import ContextVar

# Set by SiteContextMiddleware when the host is one of a site's
# ``web_domains`` (grunt.site), else ``None``.
current_web_app: ContextVar[str | None] = ContextVar("current_web_app", default=None)

__all__ = ["current_web_app"]
