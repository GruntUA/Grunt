"""Controller for the ``OnboardingStep`` DocType."""

from grunt.document.base import Document


class OnboardingStep(Document):
    """DocType controller for OnboardingStep."""

    title: str | None
    description: str | None
    action: str | None
    reference_doctype: str | None
    form_tour: str | None
    field: str | None
    value_to_validate: str | None
    report: str | None
    route: str | None
    action_label: str | None
    step_id: str | None
