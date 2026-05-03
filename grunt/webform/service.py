"""Web Form service — load form definitions and process public submissions.

Web Forms expose a subset of DocType fields as a public-facing form.
Submissions create documents in the target DocType.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from grunt.app import grunt
from grunt.metadata.field import NON_PHYSICAL_FIELDS
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Guest user identifier for anonymous submissions
GUEST_USER = "guest@grunt.local"


class WebFormService:
    """Manages web form loading, validation, and submission."""

    async def get_form(self, session: AsyncSession, route: str) -> dict[str, Any] | None:
        """Load a published web form by its route slug."""
        async with grunt.context(session):
            rows = await grunt.db.get_all(
                "WebForm",
                filters={"route": route, "is_published": True},
                fields=[
                    "name", "title", "route", "doctype", "fields", "introduction",
                    "success_message", "success_url", "allow_edit", "login_required",
                    "submit_label",
                ],
                limit=1,
            )

        return rows[0] if rows else None

    async def get_form_fields(self, session: AsyncSession, route: str) -> list[dict[str, Any]]:
        """Return the full field definitions for a web form (with DocType metadata).

        Merges the web form's selected fields with DocType field definitions.
        """
        form = await self.get_form(session, route)
        if not form:
            return []

        dt = await doctype_registry.get(form["doctype"])
        field_names = {f["fieldname"] for f in form["fields"]} if form["fields"] else set()

        result = []
        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
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
                }
            )

        return result

    async def submit(
        self,
        session: AsyncSession,
        route: str,
        data: dict[str, Any],
        user_email: str | None = None,
    ) -> dict[str, Any]:
        """Process a web form submission.

        Args:
            session: DB session.
            route: Web form route.
            data: Submitted form data.
            user_email: Authenticated user email, or None for guest.

        Returns:
            Dict with created document info.

        Raises:
            WebFormError on validation or submission failure.
        """
        form = await self.get_form(session, route)
        if not form:
            raise WebFormError("Форму не знайдено")

        if form["login_required"] and not user_email:
            raise WebFormError("Для заповнення цієї форми потрібна авторизація")

        dt = await doctype_registry.get(form["doctype"])

        # Check max submissions
        if form.get("max_submissions", 0) > 0:
            count = await self._count_submissions(session, form["doctype"])
            if count >= form["max_submissions"]:
                raise WebFormError("Досягнуто максимальну кількість відповідей")

        # Validate: only allow fields listed in the web form
        allowed_fields = {f["fieldname"] for f in form["fields"]} if form["fields"] else None
        validated = self._validate_submission(dt, data, allowed_fields)

        owner = user_email or GUEST_USER

        async with grunt.context(session, user=None):
            doc = await grunt.new_doc(form["doctype"], {**validated, "owner": owner})

        doc_id = doc["id"]

        logger.info(
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

        for field in dt.fields:
            if field.fieldtype in NON_PHYSICAL_FIELDS:
                continue
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

    async def _count_submissions(self, session: AsyncSession, doctype: str) -> int:
        """Count existing documents in the target table."""
        async with grunt.context(session):
            return await grunt.db.count(doctype)


class WebFormError(Exception):
    """Error during web form processing."""
