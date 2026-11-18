"""API keys are stored with scrypt (PERMISSIONS_PLAN step 7c, CodeQL #16); a
key stored before 7c (bare SHA-256) still works once and is rehashed."""

import hashlib

import pytest

from grunt.auth import api_key_service as svc


@pytest.fixture(autouse=True)
def _forget_verified():
    svc._VERIFIED.clear()
    yield
    svc._VERIFIED.clear()


def test_new_keys_are_scrypt_and_verify():
    full_key, _prefix, stored = svc.generate_api_key()
    assert stored.startswith("scrypt$") and not svc.needs_rehash(stored)
    assert svc.verify_key(full_key, stored)
    svc._VERIFIED.clear()
    assert not svc.verify_key(
        full_key[:-1] + "0" if full_key[-1] != "0" else full_key[:-1] + "1", stored
    )
    # Two hashes of one key differ (a salt each).
    assert stored != svc._hash_key(full_key)


def test_verified_key_is_remembered(monkeypatch):
    full_key, _prefix, stored = svc.generate_api_key()
    calls = []
    real = svc._scrypt
    monkeypatch.setattr(svc, "_scrypt", lambda *a: calls.append(1) or real(*a))
    assert svc.verify_key(full_key, stored) and svc.verify_key(full_key, stored)
    assert len(calls) == 1
    # A changed stored hash (rehashed, reissued) is checked again.
    other = svc._hash_key(full_key)
    assert svc.verify_key(full_key, other) and len(calls) == 3


@pytest.mark.asyncio
async def test_pre_7c_key_works_once_and_is_rehashed(ctx, db_session):
    full_key, prefix, _ = svc.generate_api_key()
    legacy = hashlib.sha256(full_key.encode()).hexdigest()
    user = await ctx.new_doc(
        "User", {"email": "legacy@example.com", "first_name": "L", "last_name": "K"}
    )
    key = await ctx.new_doc(
        "ApiKey",
        {
            "label": "old",
            "user_id": user["name"],
            "key_prefix": prefix,
            "key_hash": legacy,
            "is_active": True,
        },
    )
    await ctx.db._session().commit()

    assert (await svc.authenticate_api_key(full_key, db_session)) is not None
    await db_session.commit()
    stored = await ctx.db.get_value("ApiKey", key["name"], "key_hash")
    assert stored.startswith("scrypt$")
    svc._VERIFIED.clear()
    assert (await svc.authenticate_api_key(full_key, db_session)) is not None
