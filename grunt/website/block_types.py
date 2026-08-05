"""Registry of WebPage content-block types.

Mirrors the FieldType registry (grunt.metadata.field): each block type
registers a name + a Jinja template used to render it. Registering a name
also adds it to the dynamic-options registry (grunt.metadata.dynamic_options)
under BLOCK_TYPE_SOURCE, so WebPageBlock.block_type's Select dropdown always
reflects the currently-registered set — core types plus anything apps add
via hooks.py's `website_block_types`.
"""

from __future__ import annotations

from grunt.metadata.dynamic_options import register_option, register_schema

BLOCK_TYPE_SOURCE = "grunt.website.block_type"

_TEMPLATES: dict[str, str] = {}

# Shared by hero/cta_banner — same "headline + optional link" shape.
_LINK_BANNER_FIELDS = [
    {"fieldname": "subtitle", "label": "Підзаголовок", "fieldtype": "Text"},
    {"fieldname": "link_url", "label": "URL посилання", "fieldtype": "Text"},
    {"fieldname": "link_label", "label": "Текст кнопки", "fieldtype": "Text"},
]
# Shared by rich_text/columns — a single rich-text body.
_BODY_FIELDS = [{"fieldname": "body", "label": "Текст", "fieldtype": "RichText"}]


def register_block_type(name: str, template: str, fields: list[dict] | None = None) -> None:
    """Register a block type: Select option + render template + config-field schema.

    *fields* declares this type's own settings-form fields (DocField-shaped
    dicts) — stored in the dynamic-schema registry so WebPageBlock.settings
    can render exactly this type's fields instead of a shared generic pool.
    """
    register_option(BLOCK_TYPE_SOURCE, name)
    register_schema(BLOCK_TYPE_SOURCE, name, fields or [])
    _TEMPLATES[name] = template


def get_block_template(name: str) -> str | None:
    """Return the Jinja template path registered for *name*, or None if unregistered."""
    return _TEMPLATES.get(name)


# ── Built-in block types ────────────────────────────────────────────────────
register_block_type("hero", "blocks/hero.html", _LINK_BANNER_FIELDS)
register_block_type("rich_text", "blocks/rich_text.html", _BODY_FIELDS)
register_block_type(
    "image",
    "blocks/image.html",
    [{"fieldname": "image", "label": "Зображення", "fieldtype": "Image"}],
)
register_block_type("cta_banner", "blocks/cta_banner.html", _LINK_BANNER_FIELDS)
register_block_type("columns", "blocks/columns.html", _BODY_FIELDS)
register_block_type(
    "html_embed",
    "blocks/html_embed.html",
    [{"fieldname": "embed_html", "label": "HTML-код", "fieldtype": "LongText"}],
)
register_block_type(
    "form_embed",
    "blocks/form_embed.html",
    [{"fieldname": "form_route", "label": "Маршрут веб-форми", "fieldtype": "Text"}],
)
register_block_type(
    "feature_grid",
    "blocks/feature_grid.html",
    [
        {"fieldname": f"feature{i}_{sub}", "label": label, "fieldtype": fieldtype}
        for i in (1, 2, 3)
        for sub, label, fieldtype in (
            ("icon", f"Іконка {i} (emoji)", "Text"),
            ("title", f"Заголовок {i}", "Text"),
            ("text", f"Опис {i}", "Text"),
        )
    ],
)
