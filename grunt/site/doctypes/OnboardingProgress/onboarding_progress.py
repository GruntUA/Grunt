"""Controller for the ``OnboardingProgress`` DocType."""

from grunt.document.base import Document


class OnboardingProgress(Document):
    """DocType controller for OnboardingProgress."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    onboarding: str | None = None  # Onboarding
    form_tour: str | None = None  # Form tour
    step_id: str | None = None  # Step
    user: str | None = None  # User
    status: str  # Status

    # end: auto-generated types
