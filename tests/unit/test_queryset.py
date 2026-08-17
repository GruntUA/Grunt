"""Unit tests for `Document.objects` (grunt.document.queryset.QuerySet)."""

from __future__ import annotations

import pytest

from grunt.auth.doctypes.User.user import User


@pytest.mark.asyncio
async def test_filter_first_returns_none_when_no_match(ctx):
    result = await User.objects.filter(email="nobody@grunt.example.com").first()
    assert result is None


@pytest.mark.asyncio
async def test_create_returns_typed_instance(ctx):
    user = await User.objects.create(
        email="created@grunt.example.com",
        password="secret",
        first_name="Created",
        last_name="User",
        is_active=True,
    )
    assert isinstance(user, User)
    assert user.email == "created@grunt.example.com"
    assert user.name is not None


@pytest.mark.asyncio
async def test_filter_first_finds_created_doc(ctx):
    await User.objects.create(
        email="findme@grunt.example.com",
        password="secret",
        first_name="Find",
        last_name="Me",
        is_active=True,
    )

    found = await User.objects.filter(email="findme@grunt.example.com").first()
    assert found is not None
    assert isinstance(found, User)
    assert found.first_name == "Find"


@pytest.mark.asyncio
async def test_filter_all_and_count(ctx):
    for i in range(3):
        await User.objects.create(
            email=f"bulk{i}@grunt.example.com",
            password="secret",
            first_name="Bulk",
            last_name=str(i),
            is_active=True,
        )

    all_bulk = await User.objects.filter(last_name__in=["0", "1", "2"]).all()
    assert len(all_bulk) == 3

    count = await User.objects.filter(first_name="Bulk").count()
    assert count == 3


@pytest.mark.asyncio
async def test_exists(ctx):
    assert await User.objects.filter(email="ghost@grunt.example.com").exists() is False

    await User.objects.create(
        email="ghost@grunt.example.com",
        password="secret",
        first_name="Ghost",
        last_name="User",
        is_active=True,
    )
    assert await User.objects.filter(email="ghost@grunt.example.com").exists() is True


@pytest.mark.asyncio
async def test_get_or_create(ctx):
    user, created = await User.objects.get_or_create(
        email="getorcreate@grunt.example.com",
        defaults={"password": "secret", "first_name": "Got", "last_name": "Created"},
    )
    assert created is True
    assert user.email == "getorcreate@grunt.example.com"

    same_user, created_again = await User.objects.get_or_create(
        email="getorcreate@grunt.example.com",
        defaults={"password": "secret", "first_name": "Ignored", "last_name": "Ignored"},
    )
    assert created_again is False
    assert same_user.name == user.name
    assert same_user.first_name == "Got"


@pytest.mark.asyncio
async def test_limit_caps_results(ctx):
    for i in range(5):
        await User.objects.create(
            email=f"capped{i}@grunt.example.com",
            password="secret",
            first_name="Capped",
            last_name=str(i),
            is_active=True,
        )

    limited = await User.objects.filter(first_name="Capped").limit(2).all()
    assert len(limited) == 2
