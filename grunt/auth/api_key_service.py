"""API Key service - generation and verification of static API keys.

Key format: ``grnt_<64 hex chars>``
  - first 8 chars after prefix = key_prefix (stored in DB, used for lookup)
  - full 64 chars = key_secret (shown to the user once)

Stored as ``scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>`` - a key derivation
function, so a copy of the database doesn't make keys cheap to check offline
(PERMISSIONS_PLAN step 7c, CodeQL #16). A verified key is remembered in the
process for a few minutes: scrypt costs ~35 ms, and an integration calls often.

Keys stored before 7c are a bare SHA-256 hex digest. They still verify, and the
first successful use rehashes them with scrypt; the next release drops the old
format (an unused old key is then reissued).
  - The key_prefix is public and allows O(1) DB lookup without scanning all keys.
"""

import hashlib
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.auth.current import user_context
from grunt.auth.doctypes.User.user import User
from grunt.auth.ip_policy import ip_allowed, parse_ip_list
from grunt.auth.users import get_user_by_id
from grunt.db.api import GruntDB
from grunt.local import READ_ONLY_KEY, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry

_db = GruntDB()  # stateless: reads through the context's session

_KEY_PREFIX = "grnt_"
_KEY_BYTES = 32  # 64 hex chars


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key triple.

    Returns:
        (full_key, key_prefix, key_hash)
        - full_key:   shown to the user once, never stored
        - key_prefix: first 8 hex chars, stored in DB for lookup
        - key_hash:   scrypt of full_key, stored in DB for verification
    """
    raw = secrets.token_hex(_KEY_BYTES)  # 64 hex chars
    full_key = f"{_KEY_PREFIX}{raw}"
    key_prefix = raw[:8]
    key_hash = _hash_key(full_key)
    return full_key, key_prefix, key_hash


_SCHEME = "scrypt"
_N, _R, _P = 2**14, 8, 1
_SALT_BYTES = 16
_DKLEN = 32

# full key -> (stored hash it matched, monotonic time) - see the module doc.
_VERIFIED: dict[str, tuple[str, float]] = {}
_VERIFIED_TTL = 300.0
_VERIFIED_MAX = 1024


def _scrypt(full_key: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(full_key.encode(), salt=salt, n=n, r=r, p=p, dklen=_DKLEN)


def _hash_key(full_key: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _scrypt(full_key, salt, _N, _R, _P)
    return f"{_SCHEME}${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def needs_rehash(stored_hash: str) -> bool:
    """Stored before step 7c (a bare SHA-256) - rehash on the next use."""
    return not stored_hash.startswith(f"{_SCHEME}$")


def verify_key(full_key: str, stored_hash: str) -> bool:
    """Return True if *full_key* matches *stored_hash* (scrypt, or the old
    bare SHA-256 until the next release removes it)."""
    remembered = _VERIFIED.get(full_key)
    if (
        remembered is not None
        and remembered[0] == stored_hash
        and time.monotonic() - remembered[1] < _VERIFIED_TTL
    ):
        return True
    if needs_rehash(stored_hash):
        # Step 7c, phase 1: the pre-7c format. Removed in the next release.
        ok = secrets.compare_digest(hashlib.sha256(full_key.encode()).hexdigest(), stored_hash)
    else:
        try:
            _scheme, n, r, p, salt_hex, digest_hex = stored_hash.split("$")
            digest = _scrypt(full_key, bytes.fromhex(salt_hex), int(n), int(r), int(p))
        except ValueError:
            return False
        ok = secrets.compare_digest(digest.hex(), digest_hex)
    if ok:
        if len(_VERIFIED) >= _VERIFIED_MAX:
            _VERIFIED.clear()
        _VERIFIED[full_key] = (stored_hash, time.monotonic())
    return ok


async def authenticate_api_key(
    full_key: str,
    session: AsyncSession,
    client_ip: str | None = None,
) -> User | None:
    """Authenticate a request using an API key string.

    Returns the associated User on success, None on failure.
    Updates ``last_used_at`` in the background (best-effort).
    """
    if not full_key.startswith(_KEY_PREFIX):
        return None

    raw = full_key[len(_KEY_PREFIX) :]
    if len(raw) != _KEY_BYTES * 2:
        return None

    key_prefix = raw[:8]

    async with system_context(session):
        rows = await _db.get_all(
            "ApiKey",
            filters={"key_prefix": key_prefix, "is_active": True},
            fields=["name", "key_hash", "user_id", "expires_at", "allowed_ips"],
            limit=5,
        )

    if not rows:
        return None

    # Find matching key (there should only be one per prefix, but check all)
    matched_row = None
    for row in rows:
        stored_hash = row.get("key_hash") or ""
        if verify_key(full_key, stored_hash):
            matched_row = row
            break

    if not matched_row:
        log.warning("api_key.invalid_secret", prefix=key_prefix)
        return None

    if needs_rehash(matched_row.get("key_hash") or ""):
        # Step 7c: the first use of a pre-7c key stores it with scrypt.
        try:
            async with system_context(session), session.begin_nested():
                await _db.set_value("ApiKey", matched_row["name"], "key_hash", _hash_key(full_key))
            log.info("api_key.rehashed", prefix=key_prefix)
        except Exception:
            log.exception("api_key.rehash_failed", prefix=key_prefix)

    # Check expiry
    expires_at = matched_row.get("expires_at")
    if expires_at:
        exp = (
            expires_at
            if isinstance(expires_at, datetime)
            else datetime.fromisoformat(str(expires_at))
        )
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < datetime.now(UTC):
            log.info("api_key.expired", prefix=key_prefix)
            return None

    # Check IP allowlist. Fail closed: a key restricted to certain IPs must not
    # authenticate a request whose source IP could not be determined.
    allowed = parse_ip_list(matched_row.get("allowed_ips"))
    if allowed and not ip_allowed(client_ip, allowed):
        log.warning("api_key.ip_rejected", prefix=key_prefix, ip=client_ip)
        return None

    # Load user
    async with user_context(session):
        user = await get_user_by_id(matched_row["user_id"])
    if user is None or not user.is_active:
        return None

    await _limit_to_key(user, matched_row, session)

    # Update last_used_at (best-effort, don't fail the request)
    try:
        async with system_context(session):
            await _db.set_value("ApiKey", matched_row["name"], "last_used_at", datetime.now(UTC))
    except Exception:
        log.exception("suppressed_error")

    log.info("api_key.authenticated", prefix=key_prefix, user=user.email)
    return user


async def _limit_to_key(user: User, key: dict, session: AsyncSession) -> None:
    """What the key narrows its user to (PERMISSIONS_PLAN step 7): only the
    key's roles out of the user's (scopes kept); read-only - no writes. The
    user's own data isn't touched: the request's user is a copy.

    The flag and the roles come from one statement - one snapshot: an edit
    committed between two reads could pair the old flag with the new roles."""
    read_only, roles = await _key_scope(session, key["name"])
    if not roles and not read_only:
        return
    user.data = dict(user.data)
    if roles:
        rows = [r for r in user.data.get("role_rows") or [] if r.get("role_name") in roles]
        user.data["role_rows"] = rows
        user.data["roles"] = [r for r in user.data.get("roles") or [] if r in roles]
    if read_only:
        user.data[READ_ONLY_KEY] = True


async def _key_scope(session: AsyncSession, key_name: str) -> tuple[bool, set[str]]:
    """``(read_only, roles)`` of the key *key_name*, read in one query."""
    key_meta = await doctype_registry.get_meta("ApiKey")
    role_meta = await doctype_registry.get_meta("ApiKeyRole")
    if key_meta is None or role_meta is None:
        return False, set()
    key_t, role_t = key_meta.table, role_meta.table
    stmt = (
        select(key_t.c.read_only, role_t.c.role_name)
        .select_from(
            key_t.outerjoin(
                role_t,
                and_(role_t.c.parent_name == key_t.c.name, role_t.c.parent_doctype == "ApiKey"),
            )
        )
        .where(key_t.c.name == key_name)
    )
    rows = (await session.execute(stmt)).all()
    read_only = any(bool(r[0]) for r in rows)
    return read_only, {r[1] for r in rows if r[1]}
