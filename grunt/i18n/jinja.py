"""Jinja2 i18n globals — ``{{ _("Sign in") }}`` in website, print and mail templates.

Strings resolve against the current language (request, or a
:func:`grunt.i18n.use_language` block when rendering for someone else), and are
picked up by the extractor from ``.html`` / ``.j2`` / ``.jinja`` files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.i18n.service import _, ngettext, pgettext, translation_service

if TYPE_CHECKING:
    from jinja2 import Environment


def install(env: Environment) -> Environment:
    """Expose ``_`` / ``pgettext`` / ``ngettext`` / ``current_language()`` as template globals."""
    env.globals["_"] = _
    env.globals["pgettext"] = pgettext
    env.globals["ngettext"] = ngettext
    env.globals["current_language"] = translation_service.get_lang
    return env
