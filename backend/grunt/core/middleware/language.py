"""Language middleware — sets the current language from the Accept-Language header."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from grunt.core.i18n.service import _current_lang, translation_service

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

SUPPORTED = {"uk", "en"}


class LanguageMiddleware(BaseHTTPMiddleware):
    """Read Accept-Language header and set the per-request language context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        lang = _parse_accept_language(request.headers.get("accept-language", ""))
        token = translation_service.set_lang(lang)
        try:
            return await call_next(request)
        finally:
            _current_lang.reset(token)


def _parse_accept_language(header: str) -> str:
    """Return the best supported language from an Accept-Language header.

    Falls back to 'uk' if nothing matches.
    """
    if not header:
        return "uk"
    for part in header.split(","):
        lang = part.split(";")[0].strip().lower()[:2]
        if lang in SUPPORTED:
            return lang
    return "uk"
