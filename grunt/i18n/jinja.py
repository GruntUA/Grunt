"""Jinja2 i18n globals - ``{{ _("Sign in") }}`` in website, print and mail templates.

Strings resolve against the current language (request, or a
:func:`grunt.i18n.use_language` block when rendering for someone else), and are
picked up by the extractor from ``.html`` / ``.j2`` / ``.jinja`` files.
"""

from typing import Any

from jinja2 import Environment

from grunt.i18n.service import _, ngettext, pgettext, translation_service


def gettext(source: str, **params: Any) -> str:
    """``{{ _("Hello, %(name)s", name=user) }}`` - translated, then filled with *params*.

    Keyword arguments instead of ``_("...") % {...}``: the template reads the same
    and code scanning doesn't take the ``%`` for JavaScript arithmetic.
    """
    text = _(source)
    return text % params if params else text


def install(env: Environment) -> Environment:
    """Expose ``_`` / ``pgettext`` / ``ngettext`` / ``current_language()`` as template globals."""
    env.globals["_"] = gettext
    env.globals["pgettext"] = pgettext
    env.globals["ngettext"] = ngettext
    env.globals["current_language"] = translation_service.get_lang
    return env
