"""Server-side ``fetch_from``: copy a field from the document a Link points to.

A field declared as ``"fetch_from": "customer.city"`` takes ``city`` of the
``customer`` Link's target. The form fills it in the browser; this does the same
on every write, so documents created through the API or from code (sync jobs,
hooks, imports) carry the value too. It runs before ``validate``, so
controllers can rely on fetched values.

A value is (re)fetched when the Link changed or the field is still empty -
an explicitly entered value under an unchanged Link is kept, as in the form.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType


async def apply_fetch_from(
    dt: DocType, data: dict[str, Any], before: dict[str, Any] | None = None
) -> None:
    by_link: dict[str, list[tuple[str, str]]] = {}
    for field in dt.fields:
        source = field.fetch_from or ""
        link, _, target_field = source.partition(".")
        if not target_field or "." in target_field:
            continue
        by_link.setdefault(link, []).append((field.fieldname, target_field))
    if not by_link:
        return

    links = {f.fieldname: f for f in dt.fields if f.fieldtype == "Link" and f.options}
    for link, targets in by_link.items():
        link_field = links.get(link)
        value = data.get(link)
        if link_field is None or not value:
            continue
        changed = before is None or before.get(link) != value
        wanted = [(fn, src) for fn, src in targets if changed or data.get(fn) in (None, "")]
        if not wanted:
            continue
        target = await grunt.get_meta(str(link_field.options))
        if target is None or target.doc.is_virtual:
            continue
        row = await grunt.db.get_value(
            str(link_field.options), str(value), [src for _, src in wanted], as_dict=True
        )
        if row is None:
            continue
        for fieldname, src in wanted:
            data[fieldname] = row.get(src)
