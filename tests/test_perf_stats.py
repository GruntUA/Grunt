"""Persistent perf stats: in-memory buckets → hourly ``PerfStat`` rows →
period comparison in the virtual ``PerfTrend``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from grunt.monitoring import perf


@pytest.fixture(autouse=True)
def _clean_buffers(engine):
    perf.attach_sql_counter(engine)
    perf._buffers.clear()
    yield
    perf._buffers.clear()


def _site_stats() -> dict[perf.Key, perf.Stat]:
    (stats,) = perf._buffers.values()
    return stats


def test_bucket_and_percentile():
    assert perf.bucket_of(0.3) == 0
    assert perf.bucket_of(5) == 0
    assert perf.bucket_of(5.1) == 1
    assert perf.bucket_of(99_999) == len(perf.BOUNDS_MS)

    hist = [0] * len(perf.HIST_FIELDS)
    hist[perf.bucket_of(30)] = 90  # 25..50 ms
    hist[perf.bucket_of(800)] = 10  # 500..1000 ms
    assert 25 <= perf.percentile(hist, 0.5, 900) <= 50
    assert 500 <= perf.percentile(hist, 0.95, 900) <= 900
    assert perf.percentile([0] * len(perf.HIST_FIELDS), 0.5, 0) is None


def test_overflow_bucket_is_capped_by_max():
    hist = [0] * len(perf.HIST_FIELDS)
    hist[-1] = 3
    assert perf.percentile(hist, 0.95, 42_000) <= 42_000


@pytest.mark.asyncio
async def test_measure_counts_sql_and_errors(ctx):
    with perf.measure("Span", "probe"):
        await ctx.db.get_all("User", limit=1)
        await ctx.db.get_all("User", limit=1)
    with pytest.raises(RuntimeError), perf.measure("Span", "probe"):
        raise RuntimeError("boom")

    (stat,) = _site_stats().values()
    assert stat.calls == 2
    assert stat.errors == 1
    assert stat.sql_calls >= 2


@pytest.mark.asyncio
async def test_nested_measurements_both_count_sql(ctx):
    with perf.measure("HTTP", "outer"):
        with perf.measure("Document", "save", "User"):
            await ctx.db.get_all("User", limit=1)
        await ctx.db.get_all("User", limit=1)

    by_kind = {k[1]: s for k, s in _site_stats().items()}
    assert by_kind["Document"].sql_calls == 1
    assert by_kind["HTTP"].sql_calls == 2


def test_key_cap_folds_into_other(monkeypatch):
    from grunt.site.manager import current_site

    monkeypatch.setattr(perf, "MAX_KEYS", 2)
    token = current_site.set("cap-site")
    try:
        for i in range(5):
            perf.record("RPC", f"m{i}", 1.0)
    finally:
        current_site.reset(token)
    stats = perf._buffers["cap-site"]
    endpoints = {k[2] for k in stats}
    assert perf.OTHER in endpoints
    assert sum(s.calls for s in stats.values()) == 5


@pytest.mark.asyncio
async def test_persist_inserts_then_merges(ctx):
    for ms in (10, 20, 30):
        perf.record("RPC", "app.api.ping", ms)
    stats = dict(_site_stats())
    assert await perf.persist(stats) == 1

    perf._buffers.clear()
    perf.record("RPC", "app.api.ping", 2000, error=True)
    assert await perf.persist(dict(_site_stats())) == 1

    (row,) = await ctx.db.get_all("PerfStat", fields=None)
    assert row["kind"] == "RPC"
    assert row["endpoint"] == "app.api.ping"
    assert row["calls"] == 4
    assert row["errors"] == 1
    assert row["max_ms"] == 2000
    assert row["avg_ms"] == pytest.approx((10 + 20 + 30 + 2000) / 4, abs=0.01)
    assert sum(row[f] for f in perf.HIST_FIELDS) == 4
    assert row["p95_ms"] > 1000


async def _stat(ctx, hour: datetime, endpoint: str, calls: int, ms: float, sql: int = 0):
    hist = [0] * len(perf.HIST_FIELDS)
    hist[perf.bucket_of(ms)] = calls
    stat = perf.Stat(calls=calls, total_ms=ms * calls, max_ms=ms, sql_calls=sql * calls, hist=hist)
    await perf.persist({(int(hour.timestamp()), "RPC", endpoint, ""): stat})


@pytest.mark.asyncio
async def test_trend_compares_periods(ctx):
    from grunt.monitoring.doctypes.PerfTrend.perf_trend import build_rows

    now = datetime(2026, 10, 11, 12, tzinfo=UTC)
    week_ago = now - timedelta(days=8)
    await _stat(ctx, week_ago, "slower", 50, 40, sql=2)
    await _stat(ctx, now - timedelta(hours=3), "slower", 50, 400, sql=5)
    await _stat(ctx, week_ago, "steady", 50, 40)
    await _stat(ctx, now - timedelta(hours=3), "steady", 50, 40)
    await _stat(ctx, now - timedelta(hours=3), "new", 50, 40)
    await _stat(ctx, now - timedelta(hours=3), "rare", 3, 40)
    await _stat(ctx, week_ago, "rare", 3, 4)

    rows = {r["endpoint"]: r for r in await build_rows(7, now)}
    assert rows["slower"]["p95_change"] > 100
    assert rows["slower"]["avg_change"] == pytest.approx(900, abs=0.1)
    assert rows["slower"]["sql_change"] == 3
    assert rows["steady"]["p95_change"] == 0
    assert rows["new"]["prev_calls"] is None
    assert rows["new"]["p95_change"] is None
    assert rows["rare"]["p95_change"] is None  # too few calls to call it a trend


@pytest.mark.asyncio
async def test_trend_list_reads_period_filter(ctx):
    from grunt.monitoring.doctypes.PerfTrend.perf_trend import PerfTrend

    now = datetime.now(UTC)
    await _stat(ctx, now - timedelta(days=3), "three-days-ago", 20, 40)

    week = await PerfTrend.get_list("PerfTrend", filters={"period": "7"})
    day = await PerfTrend.get_list("PerfTrend", filters={"period": "1"})
    assert [r["endpoint"] for r in week] == ["three-days-ago"]
    assert list(day) == []


def _request(path: str, template: str | None, method: str = "GET", **params):
    route = SimpleNamespace(path=template) if template else None
    return SimpleNamespace(
        scope={"route": route, "path_params": params},
        url=SimpleNamespace(path=path),
        method=method,
    )


@pytest.mark.parametrize(
    ("path", "template", "params", "expected"),
    [
        (
            "/api/v1/docs/ToDo/abc",
            "/api/v1/docs/{doctype}/{name}",
            {"doctype": "ToDo", "name": "abc"},
            ("HTTP", "GET /api/v1/docs/{doctype}/{name}", "ToDo"),
        ),
        (
            "/api/v1/docs/ToDo/abc",
            "/{doctype}/{doc_id}",
            {"doctype": "ToDo", "doc_id": "abc"},
            ("HTTP", "GET /api/v1/docs/{doctype}/{doc_id}", "ToDo"),
        ),
        (
            "/api/v1/method/grunt.api.v1.search.search",
            "/api/v1/method/{path:path}",
            {},
            ("RPC", "grunt.api.v1.search.search", None),
        ),
        ("/news/2026/some-article", "/{path:path}", {}, ("Page", "/news/*", None)),
        ("/", "/{path:path}", {}, ("Page", "/", None)),
        ("/assets/index-abc.js", "/{path:path}", {}, None),
        ("/frontend/src/main.ts", "/frontend/{path:path}", {}, None),
        ("/api/v1/health", "/api/v1/health", {}, None),
        ("/api/v1/dev/x", "/api/v1/dev/x", {}, None),
        ("/nowhere", None, {}, None),
    ],
)
def test_endpoint_naming(path, template, params, expected):
    from grunt.middleware.logging import _perf_endpoint

    assert _perf_endpoint(_request(path, template, **params)) == expected


@pytest.mark.asyncio
async def test_http_request_is_recorded(client):
    await client.get("/api/v1/docs/ToDo")
    await client.get("/api/v1/method/grunt.api.v1.nope.missing")

    keys = {(k[1], k[2], k[3]) for stats in perf._buffers.values() for k in stats}
    assert ("HTTP", "GET /api/v1/docs/{doctype}", "ToDo") in keys
    assert ("RPC", "grunt.api.v1.nope.missing", "") in keys
