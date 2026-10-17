"""Uploaded photos are stored «visually lossless»: scaled to the size limit,
re-encoded (WebP or the original format), EXIF kept with the rotation applied,
and only when that makes the file smaller."""

from __future__ import annotations

import io
import random

import pytest
from PIL import Image

import grunt
from grunt.storage import backends, files, images
from grunt.storage.images import ImageOptions, optimize_image, renamed

WEBP = ImageOptions(max_size=1000, quality=85, webp=True)
ORIGINAL = ImageOptions(max_size=1000, quality=85, webp=False)


def _photo(width: int, height: int, quality: int = 98, exif=None) -> bytes:
    """A noisy picture - compresses like a real photo, unlike a flat fill."""
    rnd = random.Random(width * height)
    image = Image.effect_noise((width, height), 40).convert("RGB")
    pixels = image.load()
    assert pixels is not None
    for _ in range(200):
        x, y = rnd.randrange(width), rnd.randrange(height)
        pixels[x, y] = (255, 0, 0)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, **({"exif": exif} if exif else {}))
    return out.getvalue()


def _screenshot(width: int, height: int) -> bytes:
    """Flat colour, lines and text - what people save as PNG."""
    from PIL import ImageDraw

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    for y in range(0, height, 24):
        draw.rectangle((10, y + 4, width - 10, y + 20), outline=(200, 200, 210))
        draw.text((16, y + 6), f"Row {y} · Рядок таблиці {y * 7}", fill=(20, 20, 20))
    out = io.BytesIO()
    image.save(out, "PNG", compress_level=1)  # fast and big, like most screenshot tools
    return out.getvalue()


def _photo_png(width: int, height: int) -> bytes:
    """Smooth shades with fine grain - a photo, saved as PNG."""
    from PIL import ImageFilter

    grain = Image.effect_noise((width, height), 60).filter(ImageFilter.GaussianBlur(1.5))
    image = Image.merge("RGB", (grain, Image.linear_gradient("L").resize((width, height)), grain))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


@pytest.mark.asyncio
async def test_large_photo_is_scaled_and_becomes_webp():
    original = _photo(2400, 1600)
    result = await optimize_image(original, "image/jpeg", WEBP)
    assert result is not None and result.content_type == "image/webp"
    assert len(result.content) < len(original)
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.size == (1000, 667)


@pytest.mark.asyncio
async def test_original_mode_keeps_jpeg_and_exif():
    exif = Image.Exif()
    exif[0x010F] = "Camera maker"  # Make
    original = _photo(2400, 1600, exif=exif.tobytes())
    result = await optimize_image(original, "image/jpeg", ORIGINAL)
    assert result is not None and result.content_type == "image/jpeg"
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.getexif()[0x010F] == "Camera maker"


@pytest.mark.asyncio
async def test_rotation_from_exif_is_applied():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° CW to display
    original = _photo(1600, 1200, exif=exif.tobytes())
    result = await optimize_image(original, "image/jpeg", WEBP)
    assert result is not None
    with Image.open(io.BytesIO(result.content)) as image:
        assert image.size == (750, 1000)  # portrait now
        assert image.getexif().get(0x0112, 1) == 1


@pytest.mark.asyncio
async def test_small_compact_photo_is_left_alone():
    original = _photo(800, 600, quality=70)
    assert await optimize_image(original, "image/jpeg", ORIGINAL) is None


@pytest.mark.asyncio
async def test_screenshot_png_becomes_lossless_webp():
    original = _screenshot(800, 600)
    result = await optimize_image(original, "image/png", WEBP)
    assert result is not None and result.content_type == "image/webp"
    with Image.open(io.BytesIO(original)) as a, Image.open(io.BytesIO(result.content)) as b:
        assert a.convert("RGB").tobytes() == b.convert("RGB").tobytes()


@pytest.mark.asyncio
async def test_photo_saved_as_png_becomes_lossy_webp():
    original = _photo_png(800, 600)
    result = await optimize_image(original, "image/png", WEBP)
    assert result is not None and result.content_type == "image/webp"
    assert len(result.content) < len(original) / 5


@pytest.mark.asyncio
async def test_other_types_and_broken_images_are_stored_as_is():
    assert await optimize_image(b"GIF89a...", "image/gif", WEBP) is None
    assert await optimize_image(b"%PDF-1.7", "application/pdf", WEBP) is None
    assert await optimize_image(b"not a jpeg", "image/jpeg", WEBP) is None


@pytest.mark.asyncio
async def test_same_upload_gives_same_bytes():
    original = _photo(2400, 1600)
    a = await optimize_image(original, "image/jpeg", WEBP)
    b = await optimize_image(original, "image/jpeg", WEBP)
    assert a is not None and b is not None and a.content == b.content


def test_extension_follows_the_format():
    assert renamed("Фото 1.JPG", "image/webp") == "Фото 1.webp"
    assert renamed("scan.jpeg", "image/jpeg") == "scan.jpeg"
    assert renamed("photo", "image/webp") == "photo.webp"
    assert renamed("a.png", "image/png") == "a.png"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(tmp_path))


@pytest.fixture
def options(monkeypatch):
    state = {"value": WEBP}

    async def fake():
        return state["value"]

    monkeypatch.setattr(images, "image_options", fake)
    return state


@pytest.mark.asyncio
async def test_store_saves_the_compressed_copy(ctx, storage, options):
    original = _photo(2400, 1600)
    row = await files.store(original, "IMG_0001.jpg", "image/jpeg")
    assert row["file_name"] == "IMG_0001.webp"
    assert row["content_type"] == "image/webp"
    assert row["file_size"] < len(original)
    assert row["is_compressed"] and row["original_size"] == len(original)
    assert await files.read(str(row["name"])) != original

    exact = await files.store(original, "scan.jpg", "image/jpeg", compress=False)
    assert exact["file_size"] == len(original)
    assert not exact["is_compressed"] and exact["original_size"] is None


@pytest.mark.asyncio
async def test_store_keeps_images_when_compression_is_off(ctx, storage, options):
    options["value"] = None
    original = _photo(2400, 1600)
    row = await files.store(original, "IMG_0002.jpg", "image/jpeg")
    assert (row["file_name"], row["file_size"]) == ("IMG_0002.jpg", len(original))


@pytest.mark.asyncio
async def test_compress_existing_moves_every_row_of_a_blob(ctx, storage, options):
    original = _photo(2400, 1600)
    options["value"] = None
    a = await files.store(original, "a.jpg", "image/jpeg")
    b = await files.store(original, "b.jpg", "image/jpeg")
    assert a["content_hash"] == b["content_hash"]

    options["value"] = WEBP
    dry = await images.compress_existing()
    assert dry["blobs"] >= 1 and dry["after"] < dry["before"]
    assert await grunt.db.get_value("File", str(a["name"]), "file_size") == len(original)

    await images.compress_existing(apply=True)
    for row in (a, b):
        new = await grunt.db.get_value("File", str(row["name"]), "*")
        assert new["content_type"] == "image/webp"
        assert new["file_name"].endswith(".webp")
        assert new["file_size"] < len(original)
        assert new["content_hash"] != a["content_hash"]
        assert new["is_compressed"] and new["original_size"] == len(original)

    # Compressed already - a second run leaves them alone.
    compressed = await grunt.db.get_value("File", str(a["name"]), "content_hash")
    await images.compress_existing(apply=True)
    assert await grunt.db.get_value("File", str(a["name"]), "content_hash") == compressed
    assert await grunt.db.get_value("File", str(a["name"]), "original_size") == len(original)


@pytest.mark.asyncio
async def test_compression_counts_progress_and_stops_on_cancel(ctx, storage, options):
    from grunt.progress import Progress, TaskCancelledError

    options["value"] = None
    row = await files.store(_photo(2400, 1600, quality=97), "c.jpg", "image/jpeg")
    options["value"] = WEBP

    progress = Progress("Compressing images", user=None)
    progress.cancelled = True  # the user pressed cancel
    with pytest.raises(TaskCancelledError):
        await images.compress_existing(apply=True, progress=progress)
    assert not await grunt.db.get_value("File", str(row["name"]), "is_compressed")

    progress = Progress("Compressing images", user=None)
    report = await images.compress_existing(apply=True, progress=progress)
    assert progress.total == progress.done >= report["blobs"] >= 1
    assert await grunt.db.get_value("File", str(row["name"]), "is_compressed")


@pytest.mark.asyncio
async def test_start_compression_queues_the_task(ctx, options, monkeypatch):
    from grunt.errors import ApplicationError
    from grunt.storage import tasks

    queued = {}

    async def kiq(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(tasks.compress_images, "kiq", kiq)
    assert await images.start_compression() == {"queued": True}
    assert "user" in queued

    options["value"] = None
    with pytest.raises(ApplicationError):
        await images.start_compression()
