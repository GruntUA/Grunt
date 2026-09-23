"""Web Form service — load form definitions and process public submissions.

Web Forms expose a subset of DocType fields as a public-facing form.
Submissions create documents in the target DocType.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.app import grunt
from grunt.log import log

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


# Guest user identifier for anonymous submissions
GUEST_USER = "guest@grunt.local"

# WebFormField rows carrying one of these are layout markers, not real fields —
# the target DocType, never the WebFormField row, is the source of truth for
# fieldtype/options/validator/default of an ordinary field.
_LAYOUT_FIELDTYPES = {"Tab", "Section", "Column"}


def _guest_user() -> User:
    """Synthetic, non-admin identity for anonymous webform submissions."""
    from grunt.auth.doctypes.User.user import User as _User

    return _User(
        doctype="User",
        data={
            "email": GUEST_USER,
            "full_name": "Guest",
            "roles": ["Guest"],
            "is_active": True,
        },
    )


class WebFormService:
    """Manages web form loading, validation, and submission."""

    async def get_form(self, route: str) -> dict[str, Any] | None:
        """Load a published web form by its route slug, fields included.

        ``WebForm`` itself is System-Manager-only to edit (its own
        DocPermission grants nothing to Guest/All) — the actual public-access
        gate is ``is_published`` plus the *target* DocType's own create
        permission, checked in :meth:`submit`. Fetching under
        ``system_context`` here (mirroring :meth:`save_guest_file`) is what
        lets an anonymous SSR request read the form's own definition,
        including its hydrated ``fields`` child rows, without that requiring
        a matching read-permission on WebForm itself.
        """
        from grunt.context import require_session

        async with grunt.context(require_session()):
            rows = await grunt.db.get_all(
                "WebForm",
                filters={"route": route, "is_published": True},
                fields=["name"],
                limit=1,
            )
        if not rows:
            return None

        async with grunt.system_context(require_session()):
            return await grunt.get_doc("WebForm", rows[0]["name"])

    async def get_form_fields(self, route: str) -> list[dict[str, Any]]:
        """Return the form's fields, in the order chosen in the builder.

        Each ``WebFormField`` row supplies fieldname + optional overrides
        (label/required/hidden/description) and, for Tab/Section/Column rows,
        the layout marker itself. Every other property — fieldtype, options,
        validator, default — is always resolved live from the target
        DocType, so a WebForm can never drift out of sync with a field's real
        type.
        """
        form = await self.get_form(route)
        if not form:
            return []

        meta = await grunt.get_meta(form["doctype"])
        if meta is None:
            from grunt.errors import not_found

            raise not_found(f"DocType «{form['doctype']}» не знайдено")

        result: list[dict[str, Any]] = []
        for row in form["fields"] or []:
            if row.get("hidden"):
                continue

            ftype = row.get("fieldtype") or ""
            if ftype in _LAYOUT_FIELDTYPES:
                result.append(
                    {
                        "fieldname": row["fieldname"],
                        "fieldtype": ftype,
                        "label": row.get("label") or "",
                        "required": False,
                        "options": None,
                        "default": None,
                        "validator": None,
                        "collapsible": bool(row.get("collapsible")),
                    }
                )
                continue

            target = meta.get_field(row["fieldname"])
            if not target:
                # Field was removed from the target DocType after being added
                # to this form — drop it rather than surface a broken widget.
                continue

            result.append(
                {
                    "fieldname": target.fieldname,
                    "fieldtype": target.fieldtype,
                    "label": row.get("label") or target.label,
                    "required": bool(target.required) or bool(row.get("required")),
                    "options": target.options,
                    "default": target.default,
                    "validator": target.validator,
                    "description": row.get("description") or target.description,
                }
            )

        return result

    async def submit(
        self,
        route: str,
        data: dict[str, Any],
        user_email: str | None = None,
    ) -> dict[str, Any]:
        """Process a web form submission.

        Args:
            route: Web form route.
            data: Submitted form data.
            user_email: Authenticated user email, or None for guest.

        Returns:
            Dict with created document info.

        Raises:
            WebFormError on validation or submission failure.
        """
        from grunt.context import require_session

        form = await self.get_form(route)
        if not form:
            raise WebFormError("Форму не знайдено")

        if form["login_required"] and not user_email:
            raise WebFormError("Для заповнення цієї форми потрібна авторизація")

        # Check max submissions
        if form.get("max_submissions", 0) > 0:
            count = await self._count_submissions(form["doctype"])
            if count >= form["max_submissions"]:
                raise WebFormError("Досягнуто максимальну кількість відповідей")

        fields = await self.get_form_fields(route)
        validated = self._validate_submission(fields, data)

        if user_email:
            # Authenticated submitter — the ambient request context is
            # already scoped to this user by the API layer; new_doc's
            # audit_fields will set owner=user_email from it.
            doc = await grunt.new_doc(form["doctype"], validated)
            owner = user_email
        else:
            # Anonymous — run the create as a synthetic Guest identity.
            # `grunt.context(session, user=None)` would make write_guard's
            # require_user() raise (no create is possible with no user at
            # all), and running as SYSTEM_USER would bypass the target
            # DocType's create-permission rules entirely — silently letting
            # any DocType accept guest writes regardless of how it's
            # actually configured. A real (if minimal) Guest user keeps
            # permission checks meaningful: the target DocType must have an
            # explicit `role: "Guest"` (or "All") create permission.
            async with grunt.context(require_session(), user=_guest_user()):
                doc = await grunt.new_doc(form["doctype"], validated)
            owner = GUEST_USER

        doc_id = doc["name"]

        log.info(
            "webform.submitted",
            form=form["name"],
            doctype=form["doctype"],
            doc_id=doc_id,
            user=owner,
        )

        submitter_email = user_email
        if not submitter_email:
            email_field = next((f for f in fields if f.get("validator") == "email"), None)
            if email_field:
                submitter_email = validated.get(email_field["fieldname"])

        try:
            await self._notify(form, validated, doc_id, submitter_email)
        except Exception:
            log.exception("webform.notify_failed", form=form["name"], doc_id=doc_id)

        return {
            "id": doc_id,
            "name": doc.get("name", doc_id[:8]),
            "success_message": form["success_message"],
            "success_url": form.get("success_url"),
        }

    def _validate_submission(
        self,
        fields: list[dict[str, Any]],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and filter submission data against the form's resolved fields.

        *fields* is the output of :meth:`get_form_fields` — already limited to
        the fields the form actually exposes, with target-DocType and
        WebFormField-override ``required`` merged. Only real (non-layout)
        entries reach this point.
        """
        errors: list[str] = []
        validated: dict[str, Any] = {}

        for field in fields:
            if field["fieldtype"] in _LAYOUT_FIELDTYPES:
                continue

            value = data.get(field["fieldname"])

            if field["required"] and (value is None or value == ""):
                errors.append(f"Поле '{field['label']}' є обов'язковим")
                continue

            if value is not None:
                validated[field["fieldname"]] = value

        if errors:
            raise WebFormError("; ".join(errors))

        return validated

    async def _notify(
        self,
        form: dict[str, Any],
        validated: dict[str, Any],
        doc_id: str,
        submitter_email: str | None,
    ) -> None:
        """Queue the confirmation email to the submitter and/or notify_emails.

        A missing template, an EmailTemplate that's been deactivated, or any
        other failure here must never fail the submission itself — the
        document is already created by the time this runs. Callers wrap this
        in a broad try/except for that reason.
        """
        template_name = form.get("confirmation_template")
        if not template_name:
            return

        recipients: set[str] = set()
        if submitter_email:
            recipients.add(submitter_email)
        for chunk in (form.get("notify_emails") or "").replace(",", "\n").splitlines():
            addr = chunk.strip()
            if addr:
                recipients.add(addr)
        if not recipients:
            return

        from grunt.context import require_session
        from grunt.email import templates as email_templates

        session = require_session()
        context = {**validated, "doc_id": doc_id, "webform_title": form["title"]}
        for addr in recipients:
            await email_templates.queue(session, to=addr, name=template_name, context=context)

    async def _count_submissions(self, doctype: str) -> int:
        """Count existing documents in the target table."""
        from grunt.context import require_session

        async with grunt.context(require_session()):
            return await grunt.db.count(doctype)

    async def save_guest_file(self, upload: Any) -> str:
        """Store an uploaded file for an anonymous Attach-field submission.

        The JSON upload API (``grunt.storage.doctypes.File.file.upload``) requires
        an authenticated session and attributes the file to ``grunt.session.user``
        — neither holds for a guest webform POST. This stores the same way
        (storage backend + a ``File`` row) but runs the ``File`` insert under
        ``system_context`` since Guest has no reason to hold write permission on
        the File doctype itself; the target DocType's own Guest create
        permission (checked by ``submit()``) remains the real access gate.
        """
        import hashlib

        from grunt.config import settings
        from grunt.context import require_session
        from grunt.storage import get_storage_backend

        content = await upload.read()
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise WebFormError(f"Файл завеликий (макс. {settings.max_upload_size_mb} МБ)")

        content_type = upload.content_type or "application/octet-stream"
        storage = get_storage_backend()
        try:
            path = await storage.save(
                content=content, filename=upload.filename, content_type=content_type
            )
        except ValueError as exc:
            raise WebFormError(str(exc)) from exc

        async with grunt.system_context(require_session()):
            file_doc = await grunt.new_doc(
                "File",
                {
                    "file_name": upload.filename,
                    "file_url": "",
                    "path": path,
                    "content_type": content_type,
                    "content_hash": hashlib.sha256(content).hexdigest(),
                    "file_size": len(content),
                    "uploaded_by": GUEST_USER,
                    # A citizen's upload is private — staff open it via a
                    # signed URL (grunt.storage.signing).
                    "is_public": False,
                },
            )
            file_id = str(file_doc["name"])
            file_url = (
                f"/api/v1/method/grunt.storage.doctypes.File.file.get_content?file_id={file_id}"
            )
            await grunt.db.set_value("File", file_id, "file_url", file_url)

        return file_url


class WebFormError(Exception):
    """Error during web form processing."""
