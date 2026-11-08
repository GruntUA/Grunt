"""Page views: people count, bots and repeats don't; Redis batches per site."""

import pytest
import pytest_asyncio

from grunt.website import views

BROWSER = "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0"

VIEWED = {
    "name": "ViewedPage",
    "label": "Viewed Page",
    "module": "test",
    "autoname": "prompt",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "view_count", "label": "Views", "fieldtype": "Int"},
    ],
    "permissions": [{"role": "All", "read": True, "write": True, "create": True}],
}


@pytest_asyncio.fixture
async def page(ctx):
    from grunt.api.v1.meta import save_doctype, sync_doctype

    await save_doctype(doctype_data={**VIEWED, "__is_new": True})
    await sync_doctype(name=VIEWED["name"])
    await ctx.new_doc("ViewedPage", {"name": "p1", "title": "Counted"})
    await ctx.db._session().commit()
    return "p1"


class FakeRedis:
    """Just the commands views uses."""

    def __init__(self) -> None:
        self.keys: dict[str, object] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    async def hincrby(self, key, field, n):
        h = self.keys.setdefault(key, {})
        assert isinstance(h, dict)
        h[field] = h.get(field, 0) + n

    async def exists(self, key):
        return int(key in self.keys)

    async def rename(self, src, dst):
        self.keys[dst] = self.keys.pop(src)

    async def hgetall(self, key):
        return dict(self.keys.get(key) or {})  # type: ignore[call-overload]

    async def delete(self, key):
        self.keys.pop(key, None)


@pytest.mark.asyncio
async def test_people_count_bots_and_junk_dont(ctx, page, monkeypatch):
    monkeypatch.setattr(views, "_redis", lambda: None)

    assert await views.record("ViewedPage", page, "1.2.3.4", BROWSER)
    assert await views.record("ViewedPage", page, "1.2.3.4", BROWSER)  # no Redis - no repeat check
    assert not await views.record("ViewedPage", page, "1.2.3.4", "Googlebot/2.1")
    assert not await views.record("ViewedPage", page, "1.2.3.4", "")
    assert not await views.record("ViewedPage", "../x", "1.2.3.4", BROWSER)
    assert not await views.record("User", "admin", "1.2.3.4", BROWSER)  # no view_count
    assert await ctx.db.get_value("ViewedPage", page, "view_count") == 2


@pytest.mark.asyncio
async def test_redis_drops_repeats_and_flushes_per_site(ctx, page, monkeypatch):
    from grunt.site.manager import current_site, site_manager

    redis = FakeRedis()
    monkeypatch.setattr(views, "_redis", lambda: redis)
    site = current_site.get()

    assert await views.record("ViewedPage", page, "1.2.3.4", BROWSER)
    assert not await views.record("ViewedPage", page, "1.2.3.4", BROWSER)  # a repeat
    assert await views.record("ViewedPage", page, "5.6.7.8", BROWSER)
    assert redis.keys[f"grunt:views:{site}"] == {f"ViewedPage:{page}": 2}
    assert not await ctx.db.get_value("ViewedPage", page, "view_count")

    monkeypatch.setattr(site_manager, "get_sites", lambda: [site])
    assert await views.flush() == 2
    await ctx.db._session().rollback()  # see the flush's own commit
    assert await ctx.db.get_value("ViewedPage", page, "view_count") == 2
    assert f"grunt:views:{site}" not in redis.keys
    assert await views.flush() == 0


@pytest.mark.asyncio
async def test_beacon_respects_the_setting(client, ctx, page, monkeypatch):
    monkeypatch.setattr(views, "_redis", lambda: None)
    url = f"/api/v1/method/grunt.website.views.record_view?doctype=ViewedPage&name={page}"
    headers = {"User-Agent": BROWSER}

    assert (await client.post(url, headers=headers)).status_code == 200
    await ctx.db._session().rollback()
    assert await ctx.db.get_value("ViewedPage", page, "view_count") == 1

    async def off(field, default=None):
        return False if field == "count_page_views" else default

    monkeypatch.setattr(views, "get_setting", off)
    assert (await client.post(url, headers=headers)).status_code == 200
    await ctx.db._session().rollback()
    assert await ctx.db.get_value("ViewedPage", page, "view_count") == 1
