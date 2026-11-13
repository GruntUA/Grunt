"""The "Permissions" view of the DocType list: one role's rules across many
DocTypes, edited as a matrix of actions.

It is only a way of editing the ``permissions`` table of each DocType -
reading and saving go through ``DocType`` documents (``get_doc`` /
``save_doc``), so the same access check (``write`` on DocType), validation and
JSON export apply as in the DocType form.

A role may hold several rules on one DocType (different ``match``); each is a
row of the matrix, addressed by its position in ``permissions`` and checked
against its ``match`` on save - a DocType changed in the meantime is refused
(409) instead of having a different rule overwritten.
"""

from typing import Any, NoReturn

from grunt.api.context import whitelist
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.permission import ACTIONS
from grunt.permissions.roles import missing_roles
lazy from grunt.document.api import documents

# One page of the DocType list at most; a guard against unbounded requests.
MAX_DOCTYPES = 500


def _rule(index: int, perm: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "actions": [a for a in ACTIONS if a in (perm.get("actions") or [])],
        "match": perm.get("match") or None,
        "hidden_fields": list(perm.get("hidden_fields") or []),
        "readonly_fields": list(perm.get("readonly_fields") or []),
    }


async def _check_role(role: str) -> None:
    if await missing_roles([role]):
        throw(_("Role “%(role)s” not found") % {"role": role}, "NOT_FOUND")


async def _role_rules(role: str, name: str) -> dict[str, Any]:
    doc = await documents.get_doc("DocType", name)
    perms = doc.get("permissions") or []
    return {
        "doctype": name,
        "is_child": bool(doc.get("is_child")),
        "rules": [_rule(i, p) for i, p in enumerate(perms) if p.get("role") == role],
    }


@whitelist()
async def get_role_matrix(role: str, doctypes: list[str]) -> list[dict[str, Any]]:
    """*role*'s rules on each of *doctypes*: ``{doctype, is_child, rules}``, a
    rule being ``{index, actions, match, hidden_fields, readonly_fields}``."""
    await _check_role(role)
    return [await _role_rules(role, name) for name in dict.fromkeys(doctypes[:MAX_DOCTYPES])]


@whitelist()
async def save_role_matrix(role: str, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply *changes* - ``{doctype, rules: [{index, match, original, actions}]}``
    - to *role*'s rules, one ``save_doc`` per DocType; returns them as
    :func:`get_role_matrix` does.

    Each edit names the rule as the editor loaded it: ``index``, ``match`` and
    the ``original`` actions - if any of them changed since (another editor),
    the save is refused (``CONFLICT``) instead of overwriting their change.
    ``index`` ``None`` adds a rule (without ``match``) when it grants anything -
    refused too when the role has gained a rule on that DocType meanwhile.
    A rule left without actions is removed, unless it carries a ``match`` or
    field lists - those stay as they are, with no actions, for the form to
    finish."""
    await _check_role(role)
    if len(changes) > MAX_DOCTYPES:
        # Nothing is written: a truncated save would drop edits the editor sees as saved.
        throw(
            _("Too many document types in one save (%(count)s, at most %(max)s)")
            % {"count": len(changes), "max": MAX_DOCTYPES},
            "VALIDATION_ERROR",
        )
    names: list[str] = []
    for change in changes:
        name = str(change.get("doctype") or "")
        doc = await documents.get_doc("DocType", name)
        perms = [dict(p) for p in doc.get("permissions") or []]
        had_rules = any(p.get("role") == role for p in perms)
        drop: set[int] = set()
        for edit in change.get("rules") or []:
            actions = _actions(edit.get("actions"))
            index = edit.get("index")
            if index is None:
                if had_rules:
                    _conflict(name)
                if actions:
                    perms.append({"role": role, "actions": actions})
                continue
            if (
                not isinstance(index, int)
                or not 0 <= index < len(perms)
                or perms[index].get("role") != role
                or (perms[index].get("match") or None) != (edit.get("match") or None)
                or (
                    "original" in edit
                    and _actions(perms[index].get("actions")) != _actions(edit.get("original"))
                )
            ):
                _conflict(name)
            perms[index]["actions"] = actions
            rule = perms[index]
            if not actions and not (
                rule.get("match") or rule.get("hidden_fields") or rule.get("readonly_fields")
            ):
                drop.add(index)
        perms = [p for i, p in enumerate(perms) if i not in drop]
        await documents.save_doc("DocType", name, {"permissions": perms})
        names.append(name)
    return [await _role_rules(role, name) for name in names]


def _actions(raw: Any) -> list[str]:
    """*raw* actions, known ones only, in ``ACTIONS`` order (so lists compare)."""
    return [a for a in ACTIONS if a in (raw or [])]


def _conflict(doctype: str) -> NoReturn:
    throw(
        _("Permissions of “%(doctype)s” were changed meanwhile - reload the page")
        % {"doctype": doctype},
        "CONFLICT",
    )
