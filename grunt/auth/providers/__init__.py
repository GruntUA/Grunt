"""Pluggable authentication providers.

    from grunt.auth.providers import available, get
    from grunt.auth.providers.base import AuthProvider, AuthFlowContext

See :mod:`grunt.auth.providers.base` for the contract and
``docs/guide/auth-providers.md`` for a walk-through of adding one
(declared in ``hooks.py`` as ``auth_providers``).
"""

from grunt.auth.providers.base import AuthFlowContext, AuthProvider, ProviderKind
from grunt.auth.providers.declarations import declare
from grunt.auth.providers.registry import (
    all_providers,
    available,
    describe_available,
    get,
    register,
)

__all__ = [
    "AuthFlowContext",
    "AuthProvider",
    "ProviderKind",
    "all_providers",
    "available",
    "declare",
    "describe_available",
    "get",
    "register",
]
