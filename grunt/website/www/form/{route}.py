"""Public web form — server-rendered twin of the former ``PublicWebForm.vue``.

Reuses :mod:`grunt.webform.service` (the same code the JSON API wraps) to load
the definition and process the submission. The page works with no JavaScript:
a plain ``<form method="post">`` posts back to the same URL, ``handle_post``
runs the submission, and the template re-renders with a success or error state.

SSR requests carry no session (the JWT lives in ``localStorage``), so every
submission goes through as an anonymous guest — a ``login_required`` form shows
a sign-in prompt instead of the fields.
"""

from __future__ import annotations

from typing import Any

# fieldtype → native <input type>. Anything unlisted renders as a text input.
_INPUT_TYPES = {
    "Data": "text",
    "Text": "text",
    "Int": "number",
    "Float": "number",
    "Date": "date",
    "Datetime": "datetime-local",
    "Email": "email",
    "Phone": "tel",
}
_LAYOUT_TYPES = {"Section", "Column", "Tab", "Table"}


def _prepare_fields(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the service's field list into template-ready widget descriptors."""
    prepared: list[dict[str, Any]] = []
    for field in raw:
        ftype = field["fieldtype"]
        if ftype in _LAYOUT_TYPES:
            if ftype == "Section":
                prepared.append({"kind": "section", "label": field.get("label") or ""})
            continue

        if ftype == "LongText":
            widget = "textarea"
        elif ftype == "Check":
            widget = "check"
        elif ftype == "Select":
            widget = "select"
        else:
            widget = "input"

        prepared.append(
            {
                "kind": "field",
                "fieldname": field["fieldname"],
                "label": field["label"],
                "required": bool(field.get("required")),
                "default": field.get("default") or "",
                "widget": widget,
                "input_type": _INPUT_TYPES.get(ftype, "text"),
                "number_step": "any" if ftype == "Float" else "1" if ftype == "Int" else "",
                "options": [o.strip() for o in (field.get("options") or "").split("\n") if o.strip()],
            }
        )
    return prepared


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    from grunt.webform import web_form_service

    route = (context.get("path_params") or {}).get("route", "")
    form = await web_form_service.get_form(route)
    if not form:
        context["title"] = "Форму не знайдено"
        context["load_error"] = "Форму не знайдено"
        return context

    context["title"] = form["title"]
    context["form"] = form
    context["fields"] = _prepare_fields(await web_form_service.get_form_fields(route))
    context.setdefault("form_data", {})
    return context


async def handle_post(context: dict[str, Any]) -> Any:
    from fastapi.responses import HTMLResponse

    from grunt.webform import web_form_service
    from grunt.webform.service import WebFormError

    route = (context.get("path_params") or {}).get("route", "")
    raw = await context["request"].form()
    data: dict[str, Any] = {key: raw[key] for key in raw if key != "__form"}

    # Normalise checkboxes: an unchecked box isn't posted at all → coerce to 0/1
    # so the target DocType's Check field gets a real value.
    check_names = {
        f["fieldname"]
        for f in await web_form_service.get_form_fields(route)
        if f["fieldtype"] == "Check"
    }
    for name in check_names:
        data[name] = 1 if str(data.get(name, "")).lower() in ("on", "1", "true") else 0

    try:
        result = await web_form_service.submit(route=route, data=data, user_email=None)
    except WebFormError as exc:
        context["submit_error"] = str(exc)
        context["form_data"] = dict(data)
        return context
    except Exception as exc:  # e.g. HTTPException(403) when Guest lacks create
        context["submit_error"] = str(getattr(exc, "detail", exc)) or "Помилка надсилання"
        context["form_data"] = dict(data)
        return context

    if result.get("success_url"):
        return HTMLResponse("", status_code=303, headers={"Location": result["success_url"]})

    context["submitted"] = True
    context["success_message"] = result.get("success_message") or "Форму успішно надіслано."
    return context
