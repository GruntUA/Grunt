"""Web Form module — public forms for anonymous submissions."""

from grunt.core.webform.service import WebFormService

web_form_service = WebFormService()

__all__ = ["web_form_service", "WebFormService"]
