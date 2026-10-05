"""Registry for dynamic Select-field options.

Mirrors the FieldType registry (grunt.metadata.field): plugins/apps
register named option sources at import time, and DocField declares
`options_source` instead of a static `options` string to draw from one.
Resolution happens once, at schema-serve time (grunt.api.v1.meta), so
existing consumers of `DocField.options` (frontend Select.vue included)
never need to know a source is dynamic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from grunt.metadata.field import DocField

_REGISTRY: dict[str, list[str]] = {}
# Computed sources: called at schema-serve time; items are values or (value, label).
_PROVIDERS: dict[str, Callable[[], list[str | tuple[str, str]]]] = {}
_SCHEMA_REGISTRY: dict[str, dict[str, list[dict]]] = {}


def register_option(source: str, value: str) -> None:
    """Add *value* to the named *source* list (registration order = display order)."""
    values = _REGISTRY.setdefault(source, [])
    if value not in values:
        values.append(value)


def register_option_provider(source: str, fn: Callable[[], list[str | tuple[str, str]]]) -> None:
    """Compute *source*'s options on every schema serve (e.g. the UI languages).

    *fn* returns values or ``(value, label)`` pairs; labels reach the frontend
    as the field's ``option_labels``.
    """
    _PROVIDERS[source] = fn


def _provided(source: str) -> list[tuple[str, str | None]]:
    fn = _PROVIDERS.get(source)
    if fn is None:
        return []
    return [(item, None) if isinstance(item, str) else (item[0], item[1]) for item in fn()]


def get_options(source: str) -> list[str]:
    """Return the values for *source* (registered + provided), or [] if unknown."""
    values = list(_REGISTRY.get(source, []))
    values += [v for v, _label in _provided(source) if v not in values]
    return values


def get_option_labels(source: str) -> dict[str, str]:
    """``{value: label}`` for provided options that carry a label."""
    return {v: label for v, label in _provided(source) if label}


def resolve_field_options(field: DocField) -> str | None:
    """Return the effective `options` string for *field*.

    Draws from the registry when `options_source` is set, otherwise returns
    the field's own static `options` unchanged.
    """
    if field.options_source:
        return "\n".join(get_options(field.options_source))
    return field.options


def register_schema(source: str, key: str, fields: list[dict]) -> None:
    """Register the field-list variant *fields* under *source*/*key*.

    E.g. source="grunt.website.block_type", key="hero" - a WebPageBlock row
    with block_type "hero" renders exactly these fields in its settings form.
    """
    _SCHEMA_REGISTRY.setdefault(source, {})[key] = fields


def get_schemas(source: str) -> dict[str, list[dict]]:
    """Return all registered {key: fields} variants for *source*."""
    return dict(_SCHEMA_REGISTRY.get(source, {}))
