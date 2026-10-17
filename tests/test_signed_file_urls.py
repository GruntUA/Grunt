"""Signed file URLs: attachments are private, the API hands out signed URLs, and
a signed URL opens the file without a bearer token (e.g. from ``<img src>``)."""

import time
from urllib.parse import parse_qs, urlparse

import pytest

from grunt.storage.signing import sign_all_file_urls, verify

M = "/api/v1/method/grunt.storage.doctypes.File.file"
URL = f"{M}.get_content?file_id="


def test_sign_and_verify():
    data = {"a": f"{URL}abc123", "b": f"{URL}abc123&exp=1&sig=x"}
    signed = sign_all_file_urls(data)
    assert "&exp=" in signed["a"]  # unsigned URL gets a signature
    assert signed["b"].count("&exp=") == 1  # already-signed URL left alone
    qs = parse_qs(urlparse(signed["a"]).query)
    exp, sig = int(qs["exp"][0]), qs["sig"][0]
    assert verify("abc123", exp, sig)
    assert not verify("other", exp, sig)
    assert not verify("abc123", exp, sig[:-1] + ("0" if sig[-1] != "0" else "1"))
    assert not verify("abc123", exp, sig, now=exp + 1)
    assert not verify("abc123", None, None)
    assert exp > time.time() + 11 * 3600


def test_body_without_file_urls_untouched():
    data = {"x": 1}
    assert sign_all_file_urls(data) is data


def test_signature_not_appended_to_a_foreign_host_url():
    """A get_content path riding on another origin must never be signed."""
    data = {"evil": f"https://evil.example{URL}stolenid"}
    signed = sign_all_file_urls(data)
    assert "&sig=" not in signed["evil"]


@pytest.mark.asyncio
async def test_attachment_is_private_and_opens_only_with_signature(client, auth_headers):
    up = await client.post(
        f"{M}.upload",
        files={"file": ("note.txt", b"top secret", "text/plain")},
        data={"attached_to_doctype": "User", "attached_to_id": "admin@grunt.example.com"},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]
    assert "&exp=" in url and "&sig=" in url
    file_id = parse_qs(urlparse(url).query)["file_id"][0]

    # No token, valid signature → served.
    ok = await client.get(url)
    assert ok.status_code == 200
    assert ok.content == b"top secret"

    # No token, no / forged signature → refused.
    assert (await client.get(f"{URL}{file_id}")).status_code == 401
    forged = url.rsplit("&sig=", 1)[0] + "&sig=" + "0" * 32
    assert (await client.get(forged)).status_code == 401


@pytest.mark.asyncio
async def test_unattached_upload_is_private(client, auth_headers):
    up = await client.post(
        f"{M}.upload",
        files={"file": ("notes.txt", b"private bits", "text/plain")},
        headers=auth_headers,
    )
    assert up.status_code == 200, up.text
    url = up.json()["data"]["url"]
    file_id = parse_qs(urlparse(url).query)["file_id"][0]
    assert (await client.get(f"{URL}{file_id}")).status_code == 401
    assert (await client.get(url)).status_code == 200


def test_signatures_are_stripped_before_saving():
    from grunt.storage.signing import strip_file_signatures

    signed = sign_all_file_urls(f"{URL}abc")
    html_signed = f'<img src="{signed.replace("&", "&amp;")}">'
    data = {"photo": signed, "rows": [{"body": html_signed}], "n": 3}
    assert strip_file_signatures(data) == {
        "photo": f"{URL}abc",
        "rows": [{"body": f'<img src="{URL}abc">'}],
        "n": 3,
    }


@pytest.mark.asyncio
async def test_saved_attach_value_is_stored_unsigned(ctx):
    await ctx.new_doc("User", {"email": "pic@example.com", "first_name": "P", "last_name": "C"})
    signed = sign_all_file_urls(f"{URL}pic1")
    await ctx.save_doc("User", "pic@example.com", {"avatar": signed})
    await ctx.db._session().commit()
    assert await ctx.db.get_value("User", "pic@example.com", "avatar") == f"{URL}pic1"


def test_rate_limiter_recognises_file_content_requests():
    from starlette.requests import Request

    from grunt.middleware.rate_limit import _is_file_content_request

    signed = sign_all_file_urls(f"{URL}f1")

    def req(url: str) -> Request:
        path, _, query = url.partition("?")
        return Request(
            {"type": "http", "path": path, "query_string": query.encode(), "headers": []}
        )

    assert _is_file_content_request(req(signed))
    assert _is_file_content_request(req(f"{URL}f1"))  # public files are unsigned
    assert not _is_file_content_request(req("/api/v1/method/grunt.api.v1.docs.get_list"))


@pytest.mark.asyncio
async def test_authorized_signing_handles_tuples_and_keeps_container_types(ctx):
    """_sign_in_structure must sign file URLs nested in a tuple (JSON-serialised
    as an array) and must not deep-copy/retype dict/list containers."""
    from grunt.storage import signing

    data = {"row": ("x", f"{URL}pub1"), "items": [f"{URL}pub1"]}
    # Pretend pub1 is authorized.
    signed = signing._sign_in_structure(data, {"pub1"}, signing._expiry())
    assert "&sig=" in signed["row"][1]  # tuple element signed
    assert "&sig=" in signed["items"][0]  # list element signed
    assert isinstance(signed["row"], tuple) and isinstance(signed["items"], list)
    assert signed is data  # mutated in place, same dict object
