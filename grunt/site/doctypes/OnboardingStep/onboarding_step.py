"""Controller for the ``OnboardingStep`` DocType."""

from grunt.document.base import Document


class OnboardingStep(Document):
    """DocType controller for OnboardingStep."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    description: str | None = None  # Description
    action: str | None = None  # Action
    reference_doctype: str | None = None  # Document type
    form_tour: str | None = None  # Form tour
    field: str | None = None  # Field
    value_to_validate: str | None = None  # Expected value
    report: str | None = None  # Report
    route: str | None = None  # Address
    action_label: str | None = None  # Button label
    step_id: str | None = None  # Step ID

    # end: auto-generated types
