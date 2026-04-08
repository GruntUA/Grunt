"""Auth models — legacy location, now re-exporting from User DocType controller.
"""

from __future__ import annotations

from grunt.core.doctypes.user.user import SYSTEM_USER, GruntUser

__all__ = ["GruntUser", "SYSTEM_USER"]
