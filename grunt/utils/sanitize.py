"""HTML sanitization for RichText fields."""

from __future__ import annotations

from grunt.log import log

_ALLOWED_TAGS = {"p", "br", "b", "i", "u", "s", "h2", "h3", "ul", "ol", "li", "a", "blockquote"}


def sanitize_html(html: str) -> str:
    """Sanitize HTML from RichText fields, stripping dangerous tags/attributes."""
    try:
        import nh3

        return nh3.clean(html, tags=_ALLOWED_TAGS)
    except ImportError:
        log.debug("suppressed_expected_error", exc_info=True)

    try:
        import bleach  # type: ignore[import-untyped]

        return bleach.clean(html, tags=list(_ALLOWED_TAGS), strip=True)
    except ImportError:
        log.debug("suppressed_expected_error", exc_info=True)

    # Fallback: strip all tags
    import re

    return re.sub(r"<[^>]+>", "", html)
