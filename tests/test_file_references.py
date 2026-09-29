"""Pending uploads (``attached_to_doctype`` set, no id yet) are bound to the
document on save when one of its Attach / Image / RichText fields points at
them; library files and other DocTypes' uploads are left alone."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from grunt.storage.references import file_ids_in

M = "/api/v1/method/grunt.storage.doctypes.File.file"
URL = f"{M}.get_content?file_id="


def test_file_ids_in_html():
    html = (
        f'<p><img src="{URL}img1&amp;exp=1&amp;sig=ab"></p>'
        f'<ul class="file-list"><li><a href="{URL}doc-2">a.pdf</a></li></ul>'
        '<a href="https://example.com/?file_id=nope">x</a>'
    )
    assert file_ids_in(html) == {"img1", "doc-2"}
    assert file_ids_in(None) == set()


async def _upload(client, auth_headers, name: str, doctype: str | None = None) -> tuple[str, str]:
    data = {"attached_to_doctype": doctype} if doctype else {}
    up = await client.post(
        f"{M}.upload",
        files={"file": (name, name.encode(), "text/plain")},
        data=data,
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]
    return url, parse_qs(urlparse(url).query)["file_id"][0]


async def _attached_to(client, auth_headers, file_id: str) -> tuple[str | None, str | None]:
    resp = await client.get(f"/api/v1/docs/File/{file_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    doc = resp.json()["data"]
    return doc.get("attached_to_doctype"), doc.get("attached_to_id")


@pytest.mark.asyncio
async def test_save_claims_referenced_pending_uploads(client, auth_headers):
    inline_url, inline_id = await _upload(client, auth_headers, "inline.txt", "WebPage")
    cover_url, cover_id = await _upload(client, auth_headers, "cover.txt", "WebPage")
    stray_url, stray_id = await _upload(client, auth_headers, "stray.txt", "WebPage")
    lib_url, lib_id = await _upload(client, auth_headers, "library.txt")
    other_url, other_id = await _upload(client, auth_headers, "other.txt", "User")

    resp = await client.post(
        "/api/v1/docs/WebPage",
        json={
            "title": "Files",
            "route": "/files-claim",
            "content": (
                f'<p><a href="{inline_url}">inline</a> <a href="{lib_url}">lib</a> '
                f'<a href="{other_url}">other</a></p>'
            ),
            "og_image": cover_url,
        },
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    page = resp.json()["data"]["name"]

    assert await _attached_to(client, auth_headers, inline_id) == ("WebPage", page)
    assert await _attached_to(client, auth_headers, cover_id) == ("WebPage", page)
    # Not referenced → still pending.
    assert (await _attached_to(client, auth_headers, stray_id))[1] in (None, "")
    # Library file and another DocType's pending upload are only referenced.
    assert (await _attached_to(client, auth_headers, lib_id)) in ((None, None), ("", ""))
    assert (await _attached_to(client, auth_headers, other_id))[1] in (None, "")

    # A later edit claims newly referenced pending uploads too.
    resp = await client.put(
        f"/api/v1/docs/WebPage/{page}",
        json={"content": f'<a href="{stray_url}">stray</a>'},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert await _attached_to(client, auth_headers, stray_id) == ("WebPage", page)
