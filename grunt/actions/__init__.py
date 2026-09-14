"""Document Actions — code-registered, metadata-bound custom document buttons.

An *action* is a named unit of behaviour that an app registers in code
(``@doc_action(...)``); a DocType then *binds* zero or more registered actions
through its ``actions`` child table (see ``DocTypeAction`` /
``grunt/metadata/doctypes/DocTypeAction``). The binding row is where a
low-code admin picks an action from the registry and, optionally, overrides
its label / button group / variant or gates it with a JS ``condition``.

Registering an action also feeds its key into the dynamic-options registry
under ``DOC_ACTION_SOURCE`` so ``DocTypeAction.action``'s Select dropdown
always reflects the currently-registered set — mirroring how
``grunt.website.block_types`` populates ``WebPageBlock.block_type``.

Flow at runtime:

* the frontend reads ``dt.actions`` (bindings, enriched with registry
  defaults by ``grunt.api.v1.meta._dump_doctype``) and renders a toolbar
  button per visible binding;
* clicking a button calls ``POST /api/v1/method/grunt.actions.run`` with the
  DocType, the action key and the document id — if the action declares
  ``fields`` the toolbar first opens a form dialog and sends the collected
  values as ``args``;
* :func:`run` re-checks that the key is actually bound on that DocType,
  enforces the action's ``roles``, loads the document (which enforces read
  permission) and awaits the handler.

Handler contract::

    @doc_action("recalc", label="Перерахувати", doctypes=["Актив"])
    async def recalc(doc: dict, *, args: dict) -> dict | str | None:
        ...
        return {"message": "Готово", "refresh": True}

``doc`` is the document as a plain dict. Return a dict to pass data back to
the client (``message`` is toasted, ``refresh`` truthy reloads the form), or a
bare string (treated as ``{"message": ...}``), or nothing.
"""

from __future__ import annotations

import grunt
from grunt.actions.registry import (
    DOC_ACTION_SOURCE,
    DocAction,
    actions_for_doctype,
    doc_action,
    get_doc_action,
    register_doc_action,
)
from grunt.log import log

__all__ = [
    "DOC_ACTION_SOURCE",
    "DocAction",
    "actions_for_doctype",
    "doc_action",
    "enrich_doctype_actions",
    "get_doc_action",
    "list_doc_actions",
    "load_app_doc_actions",
    "register_doc_action",
    "run",
]


def load_app_doc_actions(module_paths: list[str], *, app: str | None = None) -> None:
    """Import each dotted module path so its ``@doc_action`` decorators run.

    Called from ``grunt.main`` for every installed app that declares
    ``doc_actions = [...]`` in its ``hooks.py``.
    """
    import importlib

    for mod_path in module_paths:
        try:
            importlib.import_module(mod_path)
            log.info("doc_actions.module_loaded", module=mod_path, app=app)
        except Exception as exc:  # pragma: no cover - defensive, mirrors hooks loader
            log.warning("doc_actions.module_error", module=mod_path, app=app, error=str(exc))


def enrich_doctype_actions(data: dict) -> None:
    """Attach registry-derived defaults to a serialized DocType's ``actions``.

    Mutates *data* in place (the dict produced by ``DocType.model_dump()``):

    * every binding row gains resolved ``_label`` / ``_icon`` / ``_variant`` /
      ``_group`` / ``_confirm`` / ``_missing`` keys so the frontend renders
      without a second lookup;
    * ``_action_catalog`` lists every action registered for this DocType, for
      the Studio binding editor.
    """
    doctype_name = data.get("name") or ""
    catalog = [
        {
            "key": a.key,
            "label": a.label,
            "icon": a.icon,
            "group": a.group,
            "variant": a.variant,
            "confirm": a.confirm,
            "fields": a.fields,
            "module": a.module,
        }
        for a in actions_for_doctype(doctype_name)
    ]
    data["_action_catalog"] = catalog

    for row in data.get("actions") or []:
        spec = get_doc_action(row.get("action") or "")
        if spec is None:
            row["_missing"] = True
            row["_label"] = row.get("label") or row.get("action") or "?"
            continue
        row["_missing"] = False
        row["_label"] = row.get("label") or spec.label
        row["_icon"] = row.get("icon") or spec.icon
        row["_variant"] = row.get("variant") or spec.variant
        row["_group"] = row.get("group") or spec.group
        row["_confirm"] = spec.confirm
        row["_fields"] = spec.fields


@grunt.whitelist()
async def list_doc_actions(doctype: str | None = None) -> list[dict]:
    """Return registered actions, optionally filtered to those bound-able on *doctype*."""
    specs = actions_for_doctype(doctype) if doctype else list(_all_specs())
    return [
        {
            "key": a.key,
            "label": a.label,
            "icon": a.icon,
            "group": a.group,
            "variant": a.variant,
            "confirm": a.confirm,
            "fields": a.fields,
            "doctypes": a.doctypes,
            "roles": a.roles,
            "module": a.module,
        }
        for a in specs
    ]


def _all_specs():
    from grunt.actions.registry import _REGISTRY

    return _REGISTRY.values()


@grunt.whitelist()
async def run(doctype: str, action: str, doc_id: str, args: dict | None = None) -> dict:
    """Execute a document action.

    *action* must be a key that is both registered in code **and** bound on
    *doctype* via its ``actions`` table — an unbound key is rejected even if it
    exists in the registry, so the set of runnable actions per DocType stays
    exactly what the metadata declares.
    """
    from grunt.metadata.registry import doctype_registry

    dt = await doctype_registry.get(doctype)
    bound = {(b.action or "") for b in getattr(dt, "actions", []) or []}
    if action not in bound:
        grunt.throw(f"Дію «{action}» не підключено до {doctype}", "NOT_FOUND")

    spec = get_doc_action(action)
    if spec is None:
        grunt.throw(f"Дію «{action}» не зареєстровано", "NOT_FOUND")

    if spec.roles:
        from grunt.permissions.roles import user_has_roles

        user = await grunt.get_current_user()
        if not user_has_roles(user, [*spec.roles, "System Manager"]):
            from grunt.errors import forbidden

            raise forbidden("Недостатньо прав для цієї дії")

    doc = await grunt.get_doc(doctype, doc_id)  # enforces read permission
    # Guarantee the handler can always read the DocType/id off `doc`, even if
    # the serializer omitted them.
    doc.setdefault("doctype", doctype)
    doc.setdefault("name", doc_id)

    log.info("doc_action.run", doctype=doctype, action=action, doc_id=doc_id)
    result = await spec.run(doc, args=args or {})

    if result is None:
        return {"ok": True}
    if isinstance(result, str):
        return {"ok": True, "message": result}
    return {"ok": True, **result}


# Register the core built-in actions (core.duplicate / core.recalc / …).
from grunt.actions import builtin  # noqa: E402,F401
