"""Web Form service — load form definitions and process public submissions.

Web Forms expose a subset of DocType fields as a public-facing form.
Submissions create documents in the target DocType.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.app import grunt
from grunt.document.meta import Meta
from grunt.log import log
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


# Guest user identifier for anonymous submissions
GUEST_USER = "guest@grunt.local"


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
        """Load a published web form by its route slug."""
        from grunt.context import require_session

        async with grunt.context(require_session()):
            rows = await grunt.db.get_all(
                "WebForm",
                filters={"route": route, "is_published": True},
                fields=[
                    "name",
                    "title",
                    "route",
                    "doctype",
                    "fields",
                    "introduction",
                    "success_message",
                    "success_url",
                    "allow_edit",
                    "login_required",
                    "submit_label",
                ],
                limit=1,
            )

        return rows[0] if rows else None

    async def get_form_fields(self, route: str) -> list[dict[str, Any]]:
        """Return the full field definitions for a web form (with DocType metadata).

        Merges the web form's selected fields with DocType field definitions.
        """
        form = await self.get_form(route)
        if not form:
            return []

        dt = await doctype_registry.get(form["doctype"])
        field_names = {f["fieldname"] for f in form["fields"]} if form["fields"] else set()

        result = []
        for field in Meta(dt).get_physical_fields():
            if field_names and field.fieldname not in field_names:
                continue
            result.append(
                {
                    "fieldname": field.fieldname,
                    "fieldtype": field.fieldtype,
                    "label": field.label,
                    "required": field.required,
                    "options": field.options,
                    "default": field.default,
                    "validator": field.validator,
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

        dt = await doctype_registry.get(form["doctype"])

        # Check max submissions
        if form.get("max_submissions", 0) > 0:
            count = await self._count_submissions(form["doctype"])
            if count >= form["max_submissions"]:
                raise WebFormError("Досягнуто максимальну кількість відповідей")

        # Validate: only allow fields listed in the web form
        allowed_fields = {f["fieldname"] for f in form["fields"]} if form["fields"] else None
        validated = self._validate_submission(dt, data, allowed_fields)

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

        return {
            "id": doc_id,
            "name": doc.get("name", doc_id[:8]),
            "success_message": form["success_message"],
            "success_url": form.get("success_url"),
        }

    def _validate_submission(
        self,
        dt: Any,
        data: dict[str, Any],
        allowed_fields: set[str] | None,
    ) -> dict[str, Any]:
        """Validate and filter submission data against DocType fields."""
        errors: list[str] = []
        validated: dict[str, Any] = {}

        for field in Meta(dt).get_physical_fields():
            if allowed_fields and field.fieldname not in allowed_fields:
                continue

            value = data.get(field.fieldname)

            if field.required and (value is None or value == ""):
                errors.append(f"Поле '{field.label}' є обов'язковим")
                continue

            if value is not None:
                validated[field.fieldname] = value

        if errors:
            raise WebFormError("; ".join(errors))

        return validated

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
                    "is_public": True,
                },
            )
            file_id = str(file_doc["name"])
            file_url = (
                "/api/v1/method/grunt.storage.doctypes.File.file.get_content"
                f"?file_id={file_id}"
            )
            await grunt.db.set_value("File", file_id, "file_url", file_url)

        return file_url


class WebFormError(Exception):
    """Error during web form processing."""
