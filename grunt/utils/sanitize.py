"""HTML sanitization for RichText fields (nh3 / ammonia).

Runs on every write (``RichTextField.coerce``) and again when a public page
renders the value, so neither a crafted API call nor a row written before
sanitization existed can put script into a page.
"""

from __future__ import annotations

import nh3

# ammonia's safe default tag/attribute set covers everything the tiptap editor
# emits (StarterKit, links, images, tables); on top of it:
_EXTRA_TAGS = {"iframe"}  # video embeds — src limited to _EMBED_PREFIXES
_EXTRA_ATTRIBUTES: dict[str, set[str]] = {
    # style: font-family / font-size marks, paragraph indent, column widths;
    # class: layout hooks of imported content (e.g. a portal's image galleries)
    "*": {"style", "class"},
    "a": {"title", "target"},
    "img": {"title", "loading"},
    "iframe": {"src", "title", "width", "height", "allowfullscreen", "loading"},
    "td": {"colwidth"},
    "th": {"colwidth"},
}
_ALLOWED_STYLES = {
    "font-family",
    "font-size",
    "margin-left",
    "text-align",
    "width",
    "min-width",
}
_EMBED_PREFIXES = ("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/")


def _filter_attribute(tag: str, attr: str, value: str) -> str | None:
    if tag == "iframe" and attr == "src" and not value.startswith(_EMBED_PREFIXES):
        return None
    return value


_cleaner = nh3.Cleaner(
    tags=nh3.ALLOWED_TAGS | _EXTRA_TAGS,
    attributes={
        tag: nh3.ALLOWED_ATTRIBUTES.get(tag, set()) | _EXTRA_ATTRIBUTES.get(tag, set())
        for tag in nh3.ALLOWED_ATTRIBUTES.keys() | _EXTRA_ATTRIBUTES.keys()
    },
    attribute_filter=_filter_attribute,
    filter_style_properties=_ALLOWED_STYLES,
    url_schemes={"http", "https", "mailto", "tel"},
)


def sanitize_html(html: str) -> str:
    """Strip script, event handlers, ``javascript:`` URLs and unknown markup from *html*."""
    return _cleaner.clean(html)
