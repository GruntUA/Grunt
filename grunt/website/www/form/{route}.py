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

from grunt import _

# fieldtype → native <input type>. Anything unlisted renders as a text input.
_INPUT_TYPES = {
    "Data": "text",
    "Text": "text",
    "Int": "number",
    "Float": "number",
    "Currency": "number",
    "Date": "date",
    "Datetime": "datetime-local",
}
# A plain Text/Data field carrying one of these DocField.validator names gets
# the matching native <input type> (browser keyboard hint + basic client-side
# check) — there's no separate "Email"/"Phone" fieldtype in the framework,
# validation is opt-in via `validator` on any text field (see grunt.validators).
_VALIDATOR_INPUT_TYPES = {"email": "email", "phone": "tel"}
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
        if ftype == "HTML":
            # Static block authored in the DocType builder (System Manager) — rendered as-is.
            prepared.append({"kind": "html", "content": field.get("options") or ""})
            continue
        if ftype == "Button":
            continue

        if ftype == "LongText":
            widget = "textarea"
        elif ftype == "Check":
            widget = "check"
        elif ftype == "Select":
            widget = "select"
        elif ftype == "Attach":
            widget = "file"
        else:
            widget = "input"

        input_type = _INPUT_TYPES.get(ftype, "text")
        if input_type == "text":
            input_type = _VALIDATOR_INPUT_TYPES.get(field.get("validator") or "", input_type)

        prepared.append(
            {
                "kind": "field",
                "fieldname": field["fieldname"],
                "label": field["label"],
                "required": bool(field.get("required")),
                "default": field.get("default") or "",
                "widget": widget,
                "input_type": input_type,
                "number_step": {"Float": "any", "Currency": "0.01", "Int": "1"}.get(ftype, ""),
                # Select choices, or Data autocomplete suggestions (<datalist>).
                "options": [
                    o.strip() for o in (field.get("options") or "").split("\n") if o.strip()
                ]
                if ftype in ("Select", "Data")
                else [],
            }
        )
    return prepared


def _client_ip(request: Any) -> str:
    from grunt.auth.doctypes.UserSession.user_session import client_ip

    return client_ip(request) or "unknown"


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    from grunt.webform import web_form_service
    from grunt.webform.captcha import captcha_site_key

    route = (context.get("path_params") or {}).get("route", "")
    form = await web_form_service.get_form(route)
    if not form:
        context["title"] = _("Form not found")
        context["load_error"] = _("Form not found")
        return context

    context["title"] = form["title"]
    context["form"] = form
    context["fields"] = _prepare_fields(await web_form_service.get_form_fields(route))
    context.setdefault("form_data", {})
    site_key = await captcha_site_key()
    context["captcha_enabled"] = bool(form.get("captcha_enabled")) and site_key is not None
    context["captcha_site_key"] = site_key
    return context


async def handle_post(context: dict[str, Any]) -> Any:
    from fastapi.responses import HTMLResponse
    from starlette.datastructures import UploadFile

    from grunt.webform import web_form_service
    from grunt.webform.service import WebFormError

    route = (context.get("path_params") or {}).get("route", "")
    raw = await context["request"].form()

    # Honeypot: a field no sighted visitor sees or fills (hidden off-screen in
    # the template), so anything that lands here is almost certainly a bot
    # blindly filling every input. Answer with the normal success state —
    # don't tip it off — but skip creating anything.
    if (str(raw.get("_hp") or "")).strip():
        context["submitted"] = True
        context["success_message"] = _("Thank you! Your submission has been received.")
        return context

    form = await web_form_service.get_form(route)
    if form and form.get("captcha_enabled"):
        from grunt.webform.captcha import TOKEN_FIELD, verify_captcha

        token = str(raw.get(TOKEN_FIELD) or "")
        if not await verify_captcha(token, _client_ip(context["request"])):
            context["submit_error"] = _(
                "Could not verify that you are not a robot. Please try again."
            )
            context["form_data"] = {k: v for k, v in raw.items() if k not in ("__form", "_hp")}
            return context

    data: dict[str, Any] = {key: raw[key] for key in raw if key not in ("__form", "_hp")}

    fields = await web_form_service.get_form_fields(route)

    # Normalise checkboxes: an unchecked box isn't posted at all → coerce to 0/1
    # so the target DocType's Check field gets a real value.
    check_names = {f["fieldname"] for f in fields if f["fieldtype"] == "Check"}
    for name in check_names:
        data[name] = 1 if str(data.get(name, "")).lower() in ("on", "1", "true") else 0

    # Attach fields arrive as UploadFile objects (multipart) — store them and
    # swap in the resulting file_url, the same value shape the target
    # DocType's Attach field expects everywhere else in the app.
    attach_names = {f["fieldname"] for f in fields if f["fieldtype"] == "Attach"}
    for name in attach_names:
        upload = data.get(name)
        if not isinstance(upload, UploadFile) or not upload.filename:
            data.pop(name, None)
            continue
        try:
            data[name] = await web_form_service.save_guest_file(upload)
        except WebFormError as exc:
            context["submit_error"] = str(exc)
            context["form_data"] = {k: v for k, v in data.items() if k not in attach_names}
            return context

    try:
        result = await web_form_service.submit(route=route, data=data, user_email=None)
    except WebFormError as exc:
        context["submit_error"] = str(exc)
        context["form_data"] = dict(data)
        return context
    except Exception as exc:  # e.g. HTTPException(403) when Guest lacks create
        context["submit_error"] = str(getattr(exc, "detail", exc)) or _("Submission error")
        context["form_data"] = dict(data)
        return context

    if result.get("success_url"):
        return HTMLResponse("", status_code=303, headers={"Location": result["success_url"]})

    context["submitted"] = True
    context["success_message"] = result.get("success_message") or _(
        "The form has been submitted successfully."
    )
    return context
