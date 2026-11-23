"""DocumentNamingRule - a naming pattern for the new documents of a DocType
that meet a condition (:mod:`grunt.naming.rules`)."""

import ast

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.naming.patterns import field_tokens, parse_pattern
from grunt.naming.rules import invalidate_naming_rules
from grunt.naming.service import NAMING_SERIES
from grunt.site.manager import site_cache_key


class DocumentNamingRule(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    document_type: str  # Document type
    autoname: str  # Naming pattern
    priority: int | None = None  # Priority
    disabled: bool | None = None  # Disabled
    condition: str | None = None  # Condition

    # end: auto-generated types

    async def validate(self) -> None:
        meta = await doctype_registry.get_meta(self.document_type or "")
        if meta is None:
            throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.document_type},
                "VALIDATION_ERROR",
            )
        if meta.is_child or meta.is_singleton:
            throw(
                _("Child tables and singletons are not named by series"),
                "VALIDATION_ERROR",
            )

        pattern = (self.autoname or "").strip().removeprefix("format:")
        if not pattern or pattern in ("prompt", NAMING_SERIES):
            throw(
                _("A rule needs a naming pattern, e.g. ВХ-.YYYY.-.####"),
                "VALIDATION_ERROR",
            )
        unknown = [f for f in field_tokens(parse_pattern(pattern)) if not meta.has_field(f)]
        if unknown:
            throw(
                _("“%(doctype)s” has no fields %(fields)s")
                % {"doctype": self.document_type, "fields": ", ".join(unknown)},
                "VALIDATION_ERROR",
            )
        self.autoname = pattern

        condition = (self.condition or "").strip()
        if condition:
            try:
                ast.parse(condition, mode="eval")
            except SyntaxError as exc:
                throw(
                    _("The condition is not a valid expression: %(error)s") % {"error": exc.msg},
                    "VALIDATION_ERROR",
                )
        self.condition = condition or None

    async def after_save(self) -> None:
        invalidate_naming_rules(site_cache_key())

    async def after_delete(self) -> None:
        invalidate_naming_rules(site_cache_key())
