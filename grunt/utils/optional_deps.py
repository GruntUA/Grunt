"""Helper for optional (extras-gated) third-party dependencies.

Several features (MFA, OAuth, ...) depend on a package that isn't installed
by default — this turns a raw ``ImportError`` into a 501 response that tells
the caller which extras group to install, instead of a bare traceback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from collections.abc import Callable


def require_extra[T](loader: Callable[[], T], extras_name: str) -> T:
    """Call *loader* (which does the optional import), or raise 501.

    Usage::

        def _require_pyotp():
            def _load():
                import pyotp
                return pyotp
            return require_extra(_load, "mfa")
    """
    try:
        return loader()
    except ImportError as exc:
        raise HTTPException(
            501,
            detail=(
                f"This feature requires the '{extras_name}' extras: "
                f"uv pip install grunt[{extras_name}]"
            ),
        ) from exc
