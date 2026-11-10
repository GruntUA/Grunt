"""Preview of an unpublished page.

The Desk links a draft to its future address plus ``?preview=1``. A page
handler that found no published document asks :func:`find_unpublished`: the
document is shown when the reader - known by the session cookie - may read it.
Anyone else gets the usual 404.

A preview page is rendered as usual with ``page_preview`` in the context (the
``_preview_banner.html`` include shows it), then :func:`finish_preview` signs
its file URLs for the reader (an unpublished document's files are private) and
keeps it out of caches and search engines.
"""

from typing import Any

from fastapi import Request

import grunt
lazy from grunt.auth.session_cookie import cookie_user
lazy from grunt.permissions.rbac import permission_checker
lazy from grunt.storage.signing import sign_authorized_file_urls

PREVIEW_PARAM = "preview"
PREVIEW_URL_KEY = "__preview_url"
PREVIEW_HEADERS = {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"}


def preview_url(url: str) -> str:
    return f"{url}?{PREVIEW_PARAM}=1"


async def find_unpublished(request: Request, doctype: str, filters: dict[str, Any]) -> str | None:
    """The name of the document matching *filters*, published or not, when the
    request asks for a preview and its reader may read the document.

    Marks the request as a preview (see :func:`preview_reader`). Needs a grunt
    context.
    """

    if not request.query_params.get(PREVIEW_PARAM):
        return None
    reader = await cookie_user(request)
    dt = await grunt.get_meta(doctype)
    if reader is None or dt is None:
        return None
    rows = await grunt.db.get_all(doctype, filters=filters, limit=1)
    if not rows or not await permission_checker.check(dt, "read", rows[0], user=reader.email):
        return None
    request.state.preview_reader = reader.email
    return rows[0]["name"]


def preview_reader(request: Request) -> str | None:
    """Email of who is previewing this request's page; ``None`` for a regular page."""
    return getattr(request.state, "preview_reader", None)


async def finish_preview(request: Request, html: str, headers: dict[str, str]) -> str:
    """For a preview: *html* with its file URLs signed for the reader; *headers*
    get the no-cache / noindex ones. A regular page passes through."""

    reader = preview_reader(request)
    if reader is None:
        return html
    headers.update(PREVIEW_HEADERS)
    return await sign_authorized_file_urls(html, reader)
