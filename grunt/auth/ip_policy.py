"""IP allowlists — for API keys (``ApiKey.allowed_ips``) and sign-in by role
(``Role.allowed_ips``).

Entries are single addresses or CIDR networks, separated by commas or newlines.
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


# https://www.cloudflare.com/ips/ — edge ranges that set CF-Connecting-IP.
CLOUDFLARE_RANGES = frozenset(
    {
        "173.245.48.0/20",
        "103.21.244.0/22",
        "103.22.200.0/22",
        "103.31.4.0/22",
        "141.101.64.0/18",
        "108.162.192.0/18",
        "190.93.240.0/20",
        "188.114.96.0/20",
        "197.234.240.0/22",
        "198.41.128.0/17",
        "162.158.0.0/15",
        "104.16.0.0/13",
        "104.24.0.0/14",
        "172.64.0.0/13",
        "131.0.72.0/22",
        "2400:cb00::/32",
        "2606:4700::/32",
        "2803:f800::/32",
        "2405:b500::/32",
        "2405:8100::/32",
        "2a06:98c0::/29",
        "2c0f:f248::/32",
    }
)


def parse_ip_list(raw: str | None) -> set[str]:
    return {e for e in (p.strip() for p in re.split(r"[,\n]", raw or "")) if e}


def ip_allowed(client_ip: str | None, allowed: set[str]) -> bool:
    """True if *client_ip* is one of / inside one of *allowed* (IPs or CIDRs)."""
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


async def role_ip_allowlist(user: User) -> set[str] | None:
    """Union of ``allowed_ips`` over the user's roles that restrict sign-in.

    ``None`` — no role of the user restricts it. Roles without a list never
    widen a restricted one, so holding "All" does not lift a restriction.
    """
    import grunt

    roles = list(getattr(user, "roles", None) or [])
    if not roles:
        return None
    rows = await grunt.db.get_all(
        "Role",
        filters={"name__in": roles},
        fields=["allowed_ips"],
        limit=None,
    )
    entries: set[str] = set()
    for row in rows:
        entries |= parse_ip_list(row.get("allowed_ips"))
    return entries or None


async def sign_in_ip_allowed(user: User, client_ip: str | None) -> bool:
    allowlist = await role_ip_allowlist(user)
    return allowlist is None or ip_allowed(client_ip, allowlist)
