"""Startup - workspace (AppMenu + sidebar) seeding.

App-install orchestration (DocTypes, fixtures, print formats) lives in
``grunt.startup.app_install`` - this module only creates/updates the
``AppMenu``/``WorkspaceSidebarItem`` records themselves.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import grunt
from grunt import log
lazy from grunt.site.doctypes.AppMenu.app_menu import default_color

_FIXTURES_DIR = __import__("pathlib").Path(__file__).parent.parent / "fixtures"


async def _upsert_workspace(
    ws_name: str,
    create_fields: dict[str, Any],
    update_fields: dict[str, Any],
    sidebar_rows: list[dict[str, Any]],
    section_rows: list[dict[str, Any]] | None = None,
) -> bool:
    """Create or update one AppMenu workspace, then replace its sidebar items.

    Shared by ``seed_grunt_workspace``/``_apply_workspace_fixture``/
    ``_auto_seed_workspace`` - each builds its own create/update field dicts
    from a different data source (bundled fixture / per-app fixture /
    DocType-registry fallback, respectively - which is why the two dicts
    aren't derived from one another here), but the upsert mechanics and the
    "replace sidebar: delete then bulk-insert" step are identical in all three.

    Nothing is written for a part that already matches - ``grunt migrate``
    runs this for every app on every run.

    Only the menu's own rows are compared and replaced - rows other apps
    contributed (``source_app`` set, see :func:`_apply_menu_contribution`) stay.

    Returns True if anything was written (and logs what).
    """
    existing = await grunt.get_list("AppMenu", filters={"name": ws_name}, fields=["name"], limit=1)
    written = False

    if existing:
        ws_id = existing[0]["name"]
        current = await grunt.get_doc("AppMenu", ws_id)
        clean_update = {
            k: v
            for k, v in update_fields.items()
            if v is not None and _norm(current.get(k)) != _norm(v)
        }
        if clean_update:
            await grunt.save_doc("AppMenu", ws_id, clean_update)
            written = True
        if section_rows is not None and _rows_match(_own(current, "sections"), section_rows):
            section_rows = None
        sidebar_same = _rows_match(_own(current, "sidebar_items"), sidebar_rows)
    else:
        ws = await grunt.new_doc("AppMenu", {"name": ws_name, **create_fields})
        ws_id = ws["name"]
        sidebar_same = False
        log.info("startup.workspace_created", workspace=ws_id)

    if section_rows is not None:
        written = True
        await _replace_rows("sections", ws_id, section_rows)

    if not sidebar_same:
        written = True
        await _replace_rows("sidebar_items", ws_id, sidebar_rows)

    if written and existing:
        log.info("startup.workspace_updated", workspace=ws_id)
    return written or not existing


_CHILD_DOCTYPE = {"sections": "WorkspaceSection", "sidebar_items": "WorkspaceSidebarItem"}


def _own(doc: Any, field: str, source_app: str = "") -> list[dict[str, Any]]:
    """The rows of *field* that *source_app* put there ("" = the menu's own rows)."""
    return [r for r in doc.get(field) or [] if (r.get("source_app") or "") == source_app]


async def _replace_rows(
    field: str, ws_id: str, rows: list[dict[str, Any]], source_app: str = ""
) -> None:
    """Replace *source_app*'s rows of the menu's *field* table with *rows*."""
    doctype = _CHILD_DOCTYPE[field]
    owner = {"source_app": source_app} if source_app else {"source_app__is": "not set"}
    await grunt.db.delete(doctype, {"parent_name": ws_id, **owner})
    if rows:
        await grunt.bulk_insert(
            doctype,
            [
                {"parent_name": ws_id, "parent_doctype": "AppMenu", "parent_field": field, **row}
                for row in rows
            ],
        )


def _norm(value: Any) -> Any:
    """Stored and fixture values compared loosely: None == "", True == 1."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    return value


def _rows_match(current: list[dict[str, Any]], desired: list[dict[str, Any]]) -> bool:
    """Child rows already stored as *desired*, in order (``idx`` aside - row order is it)."""
    if len(current) != len(desired):
        return False
    return all(
        _norm(cur.get(k)) == _norm(v)
        for cur, row in zip(current, desired, strict=True)
        for k, v in row.items()
        if k != "idx"
    )


def _section_rows(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Fixture ``sections`` (section + icon) as WorkspaceSection rows; None when
    the fixture has no such key, so sections edited on the site are kept."""
    if "sections" not in data:
        return None
    return [{"section": s["section"], "icon": s.get("icon", "")} for s in data["sections"]]


def _sidebar_rows_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise fixture ``sidebar_items``/``items`` entries into WorkspaceSidebarItem rows.

    Order is the order of the list in the fixture (then of the table rows in the
    UI) - items carry no ``sequence`` of their own.
    """
    return [
        {
            "idx": i,
            "section": item.get("section", ""),
            "type": item.get("type", "DocType"),
            "label": item.get("label", ""),
            "icon": item.get("icon", ""),
            "link_to": item.get("link_to", ""),
            "show_count": item.get("show_count", False),
            "count_filters": item.get("count_filters", ""),
            "roles": item.get("roles", ""),
        }
        for i, item in enumerate(items)
    ]


def _anchors(entry: dict[str, Any]) -> dict[str, str]:
    return {"anchor_after": entry.get("after", ""), "anchor_before": entry.get("before", "")}


async def seed_grunt_workspace(session: AsyncSession, eng: Any) -> None:
    """Create or update the Grunt system workspace from fixtures/grunt_workspace.json."""
    fixture_file = _FIXTURES_DIR / "grunt_workspace.json"
    if not fixture_file.exists():
        log.warning("startup.grunt_workspace_fixture_missing", path=str(fixture_file))
        return

    data: dict[str, Any] = json.loads(fixture_file.read_text())
    ws_name: str = data["name"]

    async with grunt.system_context(session, eng):
        # Register the grunt framework itself as an installed app (once)
        if await grunt.exists("GruntInstalledApp", {"name": "grunt"}) is None:
            await grunt.new_doc(
                "GruntInstalledApp",
                {
                    "name": "grunt",
                    "title": "Grunt",
                    "version": grunt.__version__,
                    "modules": ["core"],
                },
            )
            log.info("startup.grunt_app_registered")

        await _upsert_workspace(
            ws_name,
            create_fields={
                "label": data["label"],
                "app": data.get("app", "grunt"),
                "icon": data.get("icon", ""),
                "color": data.get("color", ""),
                "description": data.get("description", ""),
                "sequence": data.get("sequence", 0),
                "home_page": data.get("home_page", ""),
                "is_hidden": data.get("is_hidden", False),
                "roles": data.get("roles", ""),
                "sidebar_style": data.get("sidebar_style", "Auto"),
            },
            update_fields={
                "label": data.get("label"),
                "icon": data.get("icon"),
                "color": data.get("color"),
                "description": data.get("description"),
                "sequence": data.get("sequence"),
                "home_page": data.get("home_page"),
                "sidebar_style": data.get("sidebar_style"),
            },
            sidebar_rows=_sidebar_rows_from_items(data.get("sidebar_items", [])),
            section_rows=_section_rows(data),
        )


async def _apply_workspace_fixture(
    records: list,
    app_name: str,
    app_meta: dict,
) -> bool:
    """Upsert AppMenu + WorkspaceSidebarItem rows from fixture data.

    A record with ``extends`` is a contribution to another app's menu
    (:func:`_apply_menu_contribution`). Returns True if the app's own menu was applied.
    """
    applied = False

    for rec in records:
        if rec.get("extends"):
            await _apply_menu_contribution(rec, app_name)
            continue
        ws_name = rec.get("name", app_name)

        create_fields: dict[str, Any] = {
            "label": rec.get("label", ws_name),
            "app": rec.get("app", app_name),
            "icon": rec.get("icon", "package"),
            "color": rec.get("color", ""),
            "description": rec.get("description", ""),
            "sequence": rec.get("sequence", 10),
            "is_hidden": rec.get("is_hidden", False),
            "roles": rec.get("roles", ""),
            "sidebar_style": rec.get("sidebar_style", "Auto"),
        }
        # home_page is a Link - omit rather than send "" when unset
        if rec.get("home_page"):
            create_fields["home_page"] = rec["home_page"]

        await _upsert_workspace(
            ws_name,
            create_fields=create_fields,
            update_fields={
                "label": rec.get("label"),
                "icon": rec.get("icon"),
                "color": rec.get("color") or default_color(ws_name),
                "description": rec.get("description"),
                "sequence": rec.get("sequence"),
                "roles": rec.get("roles"),
                "is_hidden": rec.get("is_hidden"),
                "home_page": rec.get("home_page"),
                "sidebar_style": rec.get("sidebar_style"),
            },
            sidebar_rows=_sidebar_rows_from_items(rec.get("sidebar_items", rec.get("items", []))),
            section_rows=_section_rows(rec),
        )

        applied = True

    return applied


async def _apply_menu_contribution(rec: dict[str, Any], app_name: str) -> bool:
    """Put *app_name*'s sections and items into the menu of the app it extends::

        {"doctype": "AppMenu", "extends": "inventory",
         "sections": [{"section": "Crystal Finance", "icon": "landmark", "after": "Агенти"}],
         "items": [{"section": "Crystal Finance", "link_to": "CrystalFinanceCard", ...},
                   {"section": "Налаштування", "link_to": "CrystalFinanceSettings",
                    "after": "InventorySettings"}]}

    The rows are stored with ``source_app = app_name``, so the base app's own
    sync leaves them alone and uninstalling *app_name* removes them. ``after``/
    ``before`` (a section name for sections, an item's ``link_to`` or label for
    items) place them among the base rows when the menu is read
    (:func:`order_menu`). Returns True if anything was written.
    """
    target = rec["extends"]
    if await grunt.exists("AppMenu", {"name": target}) is None:
        log.warning("startup.menu_contribution_target_missing", app=app_name, target=target)
        return False
    current = await grunt.get_doc("AppMenu", target)

    item_rows = [
        {**row, "source_app": app_name, **_anchors(item)}
        for row, item in zip(
            _sidebar_rows_from_items(rec.get("items", [])), rec.get("items", []), strict=True
        )
    ]
    section_rows = [
        {"section": s["section"], "icon": s.get("icon", ""), "source_app": app_name, **_anchors(s)}
        for s in rec.get("sections", [])
    ]

    written = False
    for field, rows in (("sections", section_rows), ("sidebar_items", item_rows)):
        if not _rows_match(_own(current, field, app_name), rows):
            await _replace_rows(field, target, rows, source_app=app_name)
            written = True
    if written:
        log.info("startup.menu_contribution_applied", app=app_name, target=target)
    return written


async def _auto_seed_workspace(
    app_name: str,
    app_meta: dict,
    app_doctypes: list,
) -> None:
    """Create/update workspace from registry DocTypes (fallback when no fixture)."""
    await _upsert_workspace(
        app_name,
        create_fields={
            "label": app_meta.get("title", app_name),
            "app": app_name,
            "icon": "package",
            "description": app_meta.get("description", ""),
            "sequence": app_meta.get("sequence", 10),
            "is_hidden": False,
            "roles": "",
        },
        update_fields={
            "label": app_meta.get("title", app_name),
            "description": app_meta.get("description", ""),
        },
        sidebar_rows=[
            {
                "idx": seq,
                "section": app_meta.get("title", app_name),
                "type": "DocType",
                "label": dt.label,
                # Leave blank when the DocType has no icon of its own - the
                # workspace API fills it from the DocType meta on read, and the
                # frontend falls back to a generic icon.
                "icon": getattr(dt, "icon", None) or "",
                "link_to": dt.name,
                "show_count": True,
                "count_filters": "",
                "roles": "",
            }
            for seq, dt in enumerate(app_doctypes, start=1)
        ],
    )
