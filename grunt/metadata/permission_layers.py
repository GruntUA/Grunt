"""Site layer over an app's permission rules (PERMISSIONS_PLAN step 6e).

A stored DocType definition holds two sets of rules:

* ``permissions`` - the rules in force on this site;
* ``permissions_base`` - what the app's JSON (or the core's) said, as of the
  last sync.

``permissions == permissions_base`` - the site never changed them: they follow
the JSON on every ``grunt migrate``. Otherwise the site's rules stay and only
the base moves; when the JSON changed while the site's own rules were kept,
``permissions_outdated`` flags it for review - the DocType form says so and
offers the difference and "restore the app's rules".

The same rule for core and app DocTypes (:func:`take_json_rules`).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission


def dump(rules: Sequence[DocPermission] | None) -> list[dict] | None:
    return None if rules is None else [r.model_dump() for r in rules]


def customized(dt: DocType) -> bool:
    """The site's rules differ from the JSON's (as of the last sync)."""
    return dt.permissions_base is not None and dump(dt.permissions) != dump(dt.permissions_base)


@dataclass(frozen=True, slots=True)
class Rules:
    permissions: list[DocPermission]
    permissions_base: list[DocPermission]
    permissions_outdated: bool

    @property
    def kept_site_rules(self) -> bool:
        return dump(self.permissions) != dump(self.permissions_base)


def take_json_rules(stored: DocType | None, json_rules: Sequence[DocPermission]) -> Rules:
    """The rules a DocType gets when its JSON (*json_rules*) meets the stored
    definition *stored* (``None`` - a new DocType).

    Rules the site never changed follow the JSON; changed ones stay, with the
    JSON as the new base - and flagged outdated when the JSON moved meanwhile.
    A stored definition from before ``permissions_base`` existed counts as
    changed unless its rules equal the JSON (its origin is unknown).
    """
    json_rules = list(json_rules)
    if stored is None:
        return Rules(json_rules, json_rules, False)
    if stored.permissions_base is None:
        site_changed = dump(stored.permissions) != dump(json_rules)
        json_moved = site_changed
    else:
        site_changed = customized(stored)
        json_moved = dump(stored.permissions_base) != dump(json_rules)
    if not site_changed:
        return Rules(json_rules, json_rules, False)
    return Rules(
        list(stored.permissions),
        json_rules,
        stored.permissions_outdated or json_moved,
    )


def apply(dt: DocType, rules: Rules) -> None:
    dt.permissions = list(rules.permissions)
    dt.permissions_base = list(rules.permissions_base)
    dt.permissions_outdated = rules.permissions_outdated
