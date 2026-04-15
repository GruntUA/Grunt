"""Auth models — legacy location, now re-exporting from User DocType controller.
"""

from __future__ import annotations

from grunt.core.doctypes.user.user import SYSTEM_USER, User

__all__ = ["User", "SYSTEM_USER"]
