"""API keys are stored with scrypt (PERMISSIONS_PLAN step 7c, CodeQL #16); a
key stored before 7c (bare SHA-256) still works once and is rehashed."""

import pytest

from grunt.auth import api_key_service as svc

# A pre-7c record: the key and its bare SHA-256, computed once outside the tests.
LEGACY_KEY = "grnt_" + "ab" * 32
LEGACY_HASH = "d4a7de7810a8b2af190132d2e8bf1c24a775df98e0eccbba1c69afb918c27d3d"


def test_new_keys_are_scrypt_and_verify():
    full_key, _prefix, stored = svc.generate_api_key()
    assert stored.startswith("scrypt$") and not svc.needs_rehash(stored)
    assert svc.verify_key(full_key, stored)
    wrong = full_key[:-1] + ("1" if full_key.endswith("0") else "0")
    assert not svc.verify_key(wrong, stored)
    # Two hashes of one key differ (a salt each).
    assert stored != svc._hash_key(full_key)


def test_parameters_come_from_the_stored_hash():
    """A key stored with other scrypt parameters still verifies."""
    salt = b"s" * 16
    digest = svc._scrypt(LEGACY_KEY, salt, 2**14, 8, 1)
    stored = f"scrypt${2**14}$8$1${salt.hex()}${digest.hex()}"
    assert svc.verify_key(LEGACY_KEY, stored)
    assert not svc.verify_key(LEGACY_KEY, "scrypt$broken")


@pytest.mark.asyncio
async def test_verify_runs_off_the_event_loop():
    full_key, _prefix, stored = svc.generate_api_key()
    assert await svc.verify_key_async(full_key, stored)


@pytest.mark.asyncio
async def test_pre_7c_key_works_once_and_is_rehashed(ctx, db_session):
    assert svc.needs_rehash(LEGACY_HASH) and svc.verify_key(LEGACY_KEY, LEGACY_HASH)
    user = await ctx.new_doc(
        "User", {"email": "legacy@example.com", "first_name": "L", "last_name": "K"}
    )
    key = await ctx.new_doc(
        "ApiKey",
        {
            "label": "old",
            "user_id": user["name"],
            "key_prefix": LEGACY_KEY[5:13],
            "key_hash": LEGACY_HASH,
            "is_active": True,
        },
    )
    await ctx.db._session().commit()

    assert (await svc.authenticate_api_key(LEGACY_KEY, db_session)) is not None
    await db_session.commit()
    stored = await ctx.db.get_value("ApiKey", key["name"], "key_hash")
    assert stored.startswith("scrypt$")
    assert (await svc.authenticate_api_key(LEGACY_KEY, db_session)) is not None


@pytest.mark.asyncio
async def test_health_lists_active_keys_in_the_old_format(ctx):
    from grunt.monitoring.health import legacy_api_keys

    user = await ctx.new_doc(
        "User", {"email": "hk@example.com", "first_name": "H", "last_name": "K"}
    )
    full_key, prefix, stored = svc.generate_api_key()
    common = {"user_id": user["name"], "is_active": True}
    await ctx.new_doc(
        "ApiKey", {**common, "label": "new", "key_prefix": prefix, "key_hash": stored}
    )
    await ctx.new_doc(
        "ApiKey",
        {**common, "label": "old", "key_prefix": LEGACY_KEY[5:13], "key_hash": LEGACY_HASH},
    )
    await ctx.new_doc(
        "ApiKey",
        {
            **common,
            "label": "off",
            "key_prefix": "deadbeef",
            "key_hash": LEGACY_HASH,
            "is_active": False,
        },
    )
    await ctx.db._session().commit()
    assert await legacy_api_keys() == [f"old ({LEGACY_KEY[5:13]})"]


@pytest.mark.asyncio
async def test_a_failing_key_scan_keeps_the_section(ctx, monkeypatch):
    from grunt.monitoring import health

    async def broken():
        raise RuntimeError("no ApiKey table")

    monkeypatch.setattr(health, "legacy_api_keys", broken)
    rows = await health.check_users()
    assert len(rows) == 5  # the four user rows and the key row, as an error
    assert "no ApiKey table" in str(rows[-1])
