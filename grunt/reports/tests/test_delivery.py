"""Scheduled report delivery: due-date rules and the queued XLSX email."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime

import pytest

from grunt.reports.delivery import is_due, parse_recipients

TODAY = date(2026, 9, 23)  # a Wednesday


def _at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    ("frequency", "last", "due"),
    [
        (None, None, False),
        ("", None, False),
        ("Daily", None, True),
        ("Daily", date(2026, 9, 22), True),
        ("Daily", date(2026, 9, 23), False),
        ("Weekly", date(2026, 9, 17), False),
        ("Weekly", date(2026, 9, 16), True),
        ("Monthly", date(2026, 9, 1), False),
        ("Monthly", date(2026, 8, 31), True),
    ],
)
def test_is_due(frequency, last, due):
    assert is_due(frequency, _at(last) if last else None, TODAY) is due


def test_is_due_accepts_iso_string():
    assert is_due("Daily", "2026-09-22T07:00:00Z", TODAY) is True
    assert is_due("Daily", "2026-09-23T07:00:00+00:00", TODAY) is False


def test_parse_recipients():
    assert parse_recipients("a@x.ua, b@x.ua;\n c@x.ua\n\n") == ["a@x.ua", "b@x.ua", "c@x.ua"]
    assert parse_recipients(None) == []


def test_attachment_encoding_round_trip():
    from grunt.email.service import decode_attachments, encode_attachments

    stored = encode_attachments([{"filename": "r.xlsx", "mimetype": "x/y", "content": b"\x00\x01"}])
    assert decode_attachments(stored) == [
        {"filename": "r.xlsx", "mimetype": "x/y", "content": b"\x00\x01"}
    ]
    assert encode_attachments(None) is None
    assert decode_attachments(None) == []


@pytest.mark.asyncio
async def test_send_report_queues_xlsx_and_stamps_last_sent(ctx):
    import openpyxl

    from grunt.email.service import decode_attachments
    from grunt.reports.delivery import send_report_now

    doc = await ctx.new_doc(
        "Report",
        {
            "report_name": "Daily Answer",
            "report_type": "Query",
            "query": "SELECT 42 AS answer",
            "schedule_frequency": "Daily",
            "schedule_recipients": "boss@grunt.example.com, ops@grunt.example.com",
        },
    )
    await ctx.db._session().commit()

    assert await send_report_now(doc["name"]) == 2
    await ctx.db._session().commit()

    queued = await ctx.db.get_all(
        "EmailQueue",
        filters={"subject__like": "Звіт «Daily Answer»"},
        fields=["recipient", "attachments"],
        limit=None,
    )
    assert sorted(q["recipient"] for q in queued) == [
        "boss@grunt.example.com",
        "ops@grunt.example.com",
    ]
    [att] = decode_attachments(queued[0]["attachments"])
    assert att["filename"] == "Daily Answer.xlsx"
    sheet = openpyxl.load_workbook(io.BytesIO(att["content"])).active
    assert [c.value for c in sheet[1]] == ["answer"]
    assert sheet["A2"].value == 42

    report = await ctx.get_doc("Report", doc["name"])
    assert report["last_sent_at"]
