"""Password hashing (bcrypt), off the event loop.

A leaf: the ``User`` controller (hashing on save) and :mod:`grunt.auth.users`
(authentication) both use it without importing each other.
"""

import anyio.to_thread
import bcrypt


def _hash_password_sync(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _verify_password_sync(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except AttributeError, ValueError:
        return False


async def hash_password(plain: str) -> str:
    """Hash a password off the event loop.

    bcrypt is deliberately slow (~100ms+); running it inline would block every
    other request served by the same worker for that whole time.
    """
    return await anyio.to_thread.run_sync(_hash_password_sync, plain)


async def verify_password(plain: str, hashed: str | None) -> bool:
    """Verify a password off the event loop (see :func:`hash_password`)."""
    if not hashed:
        return False
    return await anyio.to_thread.run_sync(_verify_password_sync, plain, hashed)
