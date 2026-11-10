"""Provider classes declared in hooks modules (``auth_providers``), not yet imported.

A leaf: the hooks consumer writes here while apps load, and
:mod:`grunt.auth.providers.registry` imports the classes on first access - so
loading hooks never pulls in a provider, and with it the User controller.
"""

_DECLARED: list[str] = []


def declare(path: str) -> None:
    """Add ``module.Class`` to the providers imported on first access."""
    if path not in _DECLARED:
        _DECLARED.append(path)


def take() -> list[str]:
    """Hand over the declarations made since the last call, in order."""
    taken = list(_DECLARED)
    _DECLARED.clear()
    return taken
