"""Document Naming Rules - a naming pattern chosen by a condition on the new
document (another series for another department, document type, ...).

The rules of a site are few: all of them are loaded at once and cached per
process until a rule is saved or deleted. The first enabled rule of the
DocType (highest ``priority`` first) whose condition holds wins; it replaces
the DocType's ``autoname`` and the controller's own ``autoname()``.
"""

from dataclasses import dataclass
from typing import Any

lazy from simpleeval import simple_eval

from grunt.cache.bus import fanout
from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.log import log
from grunt.site.manager import site_cache_key
lazy from grunt.metadata.registry import doctype_registry

RULE_DOCTYPE = "DocumentNamingRule"

_db = GruntDB()  # stateless: reads through the context's session


@dataclass(frozen=True)
class NamingRule:
    name: str
    priority: int
    condition: str
    autoname: str


# {site: {doctype: [rules, best first]}}
_RULES: dict[str, dict[str, list[NamingRule]]] = {}
# Bumped on every invalidation: a load that started before one doesn't store
# what it read (the rows may predate the change).
_epoch = 0


@fanout
def invalidate_naming_rules(site: str | None = None) -> None:
    """Drop the cached rules of *site* (``None`` - every site). Called from the
    rule's controller after save / delete - and once more after the commit."""
    _evict(site)

    async def after_commit() -> None:
        _evict(site)

    on_commit(after_commit)


def _evict(site: str | None) -> None:
    global _epoch
    _epoch += 1
    if site is None:
        _RULES.clear()
    else:
        _RULES.pop(site, None)


async def _site_rules() -> dict[str, list[NamingRule]]:
    key = site_cache_key()
    cached = _RULES.get(key)
    if cached is not None:
        return cached
    epoch = _epoch
    loaded: dict[str, list[NamingRule]] = {}
    # A site being installed names documents before the rule table exists.
    if await doctype_registry.get_meta(RULE_DOCTYPE) is not None:
        rows = await _db.get_all(
            RULE_DOCTYPE,
            fields=["name", "document_type", "disabled", "priority", "condition", "autoname"],
            limit=None,
        )
        for r in rows:
            if r.disabled or not r.document_type or not r.autoname:
                continue
            loaded.setdefault(r.document_type, []).append(
                NamingRule(
                    name=r.name,
                    priority=int(r.priority or 0),
                    condition=(r.condition or "").strip(),
                    autoname=str(r.autoname).strip(),
                )
            )
        for rules in loaded.values():
            rules.sort(key=lambda rule: (-rule.priority, rule.name))
    if epoch == _epoch:
        _RULES[key] = loaded
    return loaded


async def rules_for(doctype: str) -> list[NamingRule]:
    """The enabled rules of *doctype*, the one to try first first."""
    return (await _site_rules()).get(doctype, [])


def condition_holds(condition: str, data: dict[str, Any]) -> bool:
    """A rule's Python condition on ``doc``; empty - always. An error counts as
    False: a typo must not number documents into another series."""
    if not condition:
        return True
    try:
        return bool(simple_eval(condition, names={"doc": _Doc(data)}))
    except Exception:  # noqa: BLE001 - any failure of a user-written expression
        log.warning("naming.rule_condition_failed", condition=condition[:200], exc_info=True)
        return False


async def matching_rule(doctype: str, data: dict[str, Any]) -> NamingRule | None:
    """The rule that names a new *doctype* document with *data*, or None."""
    for rule in await rules_for(doctype):
        if condition_holds(rule.condition, data):
            return rule
    return None


class _Doc(dict):
    """``doc.field`` as well as ``doc['field']`` / ``doc.get('field')`` in conditions."""

    def __getattr__(self, key: str) -> Any:
        return self.get(key)
