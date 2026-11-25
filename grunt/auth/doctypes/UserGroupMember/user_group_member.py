"""UserGroupMember DocType controller - child table of ``UserGroup.users``."""

from grunt.document.base import Document


class UserGroupMember(Document):
    """DocType controller for UserGroupMember (a child row of ``UserGroup.users``)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    user: str  # User

    # end: auto-generated types
