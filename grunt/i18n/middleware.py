"""Language middleware — resolves the per-request UI language.

Order of precedence:
1. explicit ``?lang=`` query parameter or ``X-Grunt-Lang`` header
2. the best match from the ``Accept-Language`` header
3. ``uk`` (framework default)

The set of acceptable languages is dynamic — :class:`TranslationService` is
seeded at startup from the active ``geo.Language`` rows (see
``grunt.startup.lifespan``) and refreshed when a ``Language`` row changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from grunt.i18n.service import _current_lang, translation_service

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

_DEFAULT = "uk"


class LanguageMiddleware(BaseHTTPMiddleware):
    """Set the per-request language context from the request, reset it after."""

    async def dispatch(self, request: Request, call_next) -> Response:
        lang = _resolve_language(request)
        token = translation_service.set_lang(lang)
        try:
            return await call_next(request)
        finally:
            _current_lang.reset(token)


def _resolve_language(request: Request) -> str:
    supported = translation_service.supported_langs()

    explicit = request.query_params.get("lang") or request.headers.get("x-grunt-lang")
    if explicit:
        code = explicit.strip().lower()[:2]
        if code in supported:
            return code

    return _parse_accept_language(request.headers.get("accept-language", ""), supported)


def apply_user_language(request: Request, language: str | None) -> None:
    """Override the request language from a resolved user's stored preference.

    No-op when the request pinned a language explicitly (``?lang=`` /
    ``X-Grunt-Lang``) or the preference is empty / unsupported.
    """
    if not language:
        return
    if request.query_params.get("lang") or request.headers.get("x-grunt-lang"):
        return
    code = language.strip().lower()[:2]
    if code in translation_service.supported_langs():
        translation_service.set_lang(code)


def _parse_accept_language(header: str, supported: set[str]) -> str:
    """Return the best supported language from an Accept-Language header."""
    if not header:
        return _DEFAULT
    for part in header.split(","):
        lang = part.split(";")[0].strip().lower()[:2]
        if lang in supported:
            return lang
    return _DEFAULT
