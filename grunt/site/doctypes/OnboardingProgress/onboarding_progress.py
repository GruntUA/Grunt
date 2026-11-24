"""Controller for the ``OnboardingProgress`` DocType."""

from grunt.document.base import Document


class OnboardingProgress(Document):
    """DocType controller for OnboardingProgress."""

    onboarding: str | None
    form_tour: str | None
    step_id: str | None
    user: str | None
    status: str | None
