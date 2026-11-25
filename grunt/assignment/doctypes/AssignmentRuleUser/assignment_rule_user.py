"""AssignmentRuleUser DocType controller - child table of ``AssignmentRule.users``."""

from grunt.document.base import Document


class AssignmentRuleUser(Document):
    """DocType controller for AssignmentRuleUser (a child row of ``AssignmentRule.users``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    user: str  # User
    weight: int | None = None  # Weight

    # end: auto-generated types
