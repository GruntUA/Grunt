"""Base contract for pluggable authentication providers.

A *provider* encapsulates one way of proving who the user is - password,
passkey (WebAuthn), an OIDC identity provider, a magic link, ... . Every
provider drives the same two-step ceremony:

* :meth:`AuthProvider.begin` - start the ceremony, hand the frontend whatever
  it needs (a redirect URL, a WebAuthn challenge, ...).
* :meth:`AuthProvider.complete` - verify the frontend's response and return the
  local :class:`~grunt.auth.doctypes.User.user.User` it authenticates.

Token issuance (JWT access + refresh, MFA gating, session tracking) is *not* a
provider concern - the generic router funnels every ``complete`` through
:func:`grunt.auth.login.issue_login`.

Providers that can also *enrol* a new factor for an already-signed-in user
(WebAuthn: "add a passkey") implement the optional
:meth:`enroll_begin` / :meth:`enroll_complete` pair and set
``supports_enrollment = True``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from grunt import _
from grunt.utils.http import public_base_url

if TYPE_CHECKING:
    from fastapi import Request

    from grunt.auth.doctypes.User.user import User

ProviderKind = Literal["redirect", "challenge"]
"""How the frontend has to drive the ceremony.

``redirect`` — ``begin`` returns ``{"redirect_url": ...}``; the browser navigates
away and comes back to a callback that feeds ``complete``.

``challenge`` — ``begin`` returns an opaque payload the frontend passes to a
browser API (e.g. ``navigator.credentials.get``); its result is posted straight
back to ``complete``.
"""


@dataclass(slots=True)
class AuthFlowContext:
    """Everything a provider needs for one ``begin``/``complete`` step."""

    request: Request
    data: dict[str, Any] = field(default_factory=dict)
    #: The bearer user, when the caller is already signed in (enrolment flows).
    user: User | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def base_url(self) -> str:
        """The public origin the browser is actually on, for links back into the SPA."""
        return public_base_url(self.request)


class AuthProvider(ABC):
    """Implement one authentication method. Subclasses self-register via
    :func:`grunt.auth.providers.registry.register`."""

    #: URL-safe identifier, e.g. ``"webauthn"`` / ``"google"``.
    name: ClassVar[str]
    #: Human label for the login screen.
    label: ClassVar[str]
    kind: ClassVar[ProviderKind]
    #: Frontend rendering hint - a lucide icon name or a well-known slug.
    icon: ClassVar[str | None] = None
    #: ``begin`` needs an account identifier (email) up front.
    requires_identifier: ClassVar[bool] = False
    #: Provider also supports enrolling the factor for a signed-in user.
    supports_enrollment: ClassVar[bool] = False

    def is_configured(self) -> bool:
        """Whether this provider is usable in the current deployment.

        Unconfigured providers are hidden from ``GET /api/v1/auth/methods`` and
        rejected by the generic endpoints.
        """
        return True

    def describe(self) -> dict[str, Any]:
        """Public metadata for the login screen."""
        return {
            "name": self.name,
            "label": _(self.label),
            "kind": self.kind,
            "icon": self.icon,
            "requires_identifier": self.requires_identifier,
            "supports_enrollment": self.supports_enrollment,
        }

    # Login ceremony

    @abstractmethod
    async def begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        """Start a sign-in ceremony. Return a JSON-serialisable payload."""

    @abstractmethod
    async def complete(self, ctx: AuthFlowContext) -> User:
        """Verify the frontend's response, return the authenticated local user."""

    # Optional: enrol a factor for a signed-in user

    async def enroll_begin(self, ctx: AuthFlowContext) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support enrollment")

    async def enroll_complete(self, ctx: AuthFlowContext) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} does not support enrollment")
