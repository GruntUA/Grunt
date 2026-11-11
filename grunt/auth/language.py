"""The UI language a user chose - to render mail and notifications to them in it.

Kept out of :mod:`grunt.i18n`, which only knows catalogs: this reads the
``User`` row.
"""

from grunt.db.api import GruntDB

_db = GruntDB()  # stateless: reads through the context's session


async def language_of(user: str | None) -> str | None:
    """Stored UI language of *user* (email) - render mail/notifications to them in it.

    Pair with :func:`grunt.i18n.use_language`; ``None`` (unknown user / no
    preference) keeps the current language.
    """
    if not user:
        return None
    try:
        # By email: ``User.name`` is the email only until the account is renamed.
        return await _db.get_value("User", {"email": user}, "language")
    except Exception:  # noqa: BLE001 - a missing user must not break delivery
        return None
