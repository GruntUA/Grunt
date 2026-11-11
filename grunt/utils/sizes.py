"""Byte counts for people."""

from grunt.i18n import _


def human_size(n: float) -> str:
    """``1536`` -> ``1.5 KB`` (units translated)."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {_(unit)}" if unit == "B" else f"{n:.1f} {_(unit)}"
        n /= 1024
    return f"{n:.1f} {_('TB')}"
