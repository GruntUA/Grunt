"""grunt data export/import — helpers (the end-to-end run needs a real site)."""

from __future__ import annotations

import io
import json
import tarfile
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import click
import pytest

from grunt.cli.data import _decode, _encode, _parse_spec, _place_files
from grunt.storage.backends import LocalStorageBackend

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_spec() -> None:
    assert _parse_spec("MltPage") == ("MltPage", {})
    assert _parse_spec("WebsiteMenuItem:menu=mlt_portal, enabled=1") == (
        "WebsiteMenuItem",
        {"menu": "mlt_portal", "enabled": "1"},
    )
    with pytest.raises(click.BadParameter):
        _parse_spec("WebsiteMenuItem:menu")


def test_values_survive_json_round_trip() -> None:
    row = {
        "at": datetime(2026, 9, 29, 10, 0, tzinfo=UTC),
        "day": date(2026, 9, 29),
        "amount": Decimal("12.50"),
        "raw": b"\x00\x01",
        "plain": {"k": "v"},
    }
    assert json.loads(json.dumps(row, default=_encode), object_hook=_decode) == row


def _bundle(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))


def test_place_files_puts_blobs_where_storage_reads_them(tmp_path: Path) -> None:
    key = "ab" * 32
    bundle = tmp_path / "b.tar"
    _bundle(
        bundle,
        {
            "data.json": b"{}",
            f"blobs/{key}": b"image",
            f"thumbs/{key}.webp": b"thumb",
            "../evil": b"x",
        },
    )
    backend = LocalStorageBackend(tmp_path / "uploads")

    assert _place_files(bundle, backend) == 1
    assert backend.path(key).read_bytes() == b"image"
    assert backend.thumbnail_path(key).read_bytes() == b"thumb"
    assert not (tmp_path / "evil").exists()
    # Content-addressed: a second run finds the blob already there.
    assert _place_files(bundle, backend) == 0


def test_place_files_rejects_bad_keys(tmp_path: Path) -> None:
    bundle = tmp_path / "b.tar"
    _bundle(bundle, {"blobs/../../escape": b"x"})
    with pytest.raises(FileNotFoundError, match="Invalid storage key"):
        _place_files(bundle, LocalStorageBackend(tmp_path / "uploads"))
