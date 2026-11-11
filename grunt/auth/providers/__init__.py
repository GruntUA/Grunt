"""Pluggable authentication providers.

    from grunt.auth.providers.registry import available, get
    from grunt.auth.providers.base import AuthProvider, AuthFlowContext

See :mod:`grunt.auth.providers.base` for the contract and
``docs/guide/auth-providers.md`` for a walk-through of adding one
(declared in ``hooks.py`` as ``auth_providers``).
"""
