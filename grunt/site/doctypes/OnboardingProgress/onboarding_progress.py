"""Controller for the ``OnboardingProgress`` DocType."""

from grunt.document.base import Document


class OnboardingProgress(Document):
    """DocType controller for OnboardingProgress."""

    onboarding: str | None
    form_tour: str | None
    step_id: str | None
    # "user" field: read it as self.data["user"] - self.user is the session user.
    status: str | None
