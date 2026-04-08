"""Grunt session management."""

from __future__ import annotations

from grunt.core.context import _user_ctx


class GruntSession:
    """Current request session information — accessible as ``grunt.session``.

    Example::

        if grunt.session.is_superadmin:
            ...
        current_user = grunt.session.user
    """

    @property
    def user(self) -> str:
        """Email of the current user, or ``"guest@grunt.local"`` for unauthenticated requests."""
        u = _user_ctx.get()
        return u.email if u else "guest@grunt.local"

    @property
    def full_name(self) -> str:
        """Full name of the current user."""
        u = _user_ctx.get()
        return u.full_name if u else "Guest"

    @property
    def roles(self) -> list[str]:
        """List of role names assigned to the current user."""
        u = _user_ctx.get()
        return u.roles if u else []

    @property
    def is_superadmin(self) -> bool:
        """Whether the current user is a superadmin."""
        u = _user_ctx.get()
        return u.is_superadmin if u else False

    def has_role(self, *roles: str) -> bool:
        """Return True if the current user has any of the given roles."""
        user_roles = set(self.roles)
        return bool(user_roles.intersection(roles))
