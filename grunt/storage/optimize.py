"""Image compression - photos are stored «visually lossless», not byte for byte.

Most of what people upload is photos straight from a phone: 4000 px wide,
several MB each, far more than any screen or printout needs. When
``SystemSettings.optimize_images`` is on, a JPEG / PNG / WebP is re-encoded
before its ``File`` row is made:

* longer side capped at ``image_max_size`` px (0 - never resized);
* ``image_format`` «WebP» - photos become lossy WebP at ``image_quality``;
  a PNG becomes lossless WebP when it is a screenshot or a diagram, lossy when
  it is a photo saved as PNG (:data:`PHOTO_RATIO`); «Original» - JPEG stays
  JPEG at ``image_quality``, PNG is re-packed losslessly;
* EXIF (rotation applied) and the colour profile are kept;
* the result is used only when it is smaller - and, for an image that
  needed no resizing, smaller by at least :data:`MIN_GAIN`, so an already
  well-compressed photo is not re-encoded (each pass costs a little quality).

Animated images, CMYK and broken files are stored as they are. The encoder is
deterministic, so the same upload gives the same bytes - content-addressed
deduplication keeps working.
"""

import asyncio
import io
from dataclasses import dataclass
from pathlib import PurePath

lazy from PIL import Image, ImageOps

from grunt.log import log
from grunt.site.settings import get_setting

OPTIMIZABLE = frozenset({"image/jpeg", "image/png", "image/webp"})
# Re-encoding an image of the right size must save at least this share.
MIN_GAIN = 0.10
# A PNG whose lossy WebP is this many times smaller than its lossless one is
# a photo: sharp text and flat colour compress well losslessly, photos don't.
PHOTO_RATIO = 3

_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@dataclass(frozen=True)
class ImageOptions:
    max_size: int = 2560
    quality: int = 85
    webp: bool = True


@dataclass(frozen=True)
class Optimized:
    content: bytes
    content_type: str


async def image_options() -> ImageOptions | None:
    """The site's settings, or None when compression is off."""
    if not await get_setting("optimize_images", True):
        return None
    return ImageOptions(
        max_size=max(0, int(await get_setting("image_max_size", 2560))),
        quality=min(100, max(1, int(await get_setting("image_quality", 85)))),
        webp=await get_setting("image_format", "WebP") == "WebP",
    )


def renamed(filename: str, content_type: str) -> str:
    """*filename* with the extension of *content_type* (``photo.JPG`` -> ``photo.webp``)."""
    ext = _EXT.get(content_type)
    if not ext:
        return filename
    current = PurePath(filename).suffix.lower()
    if current == ext or (ext == ".jpg" and current in (".jpeg", ".jpe")):
        return filename
    stem = filename[: -len(current)] if current else filename
    return stem + ext


def _optimize(content: bytes, content_type: str, opts: ImageOptions) -> Optimized | None:

    with Image.open(io.BytesIO(content)) as source:
        if getattr(source, "n_frames", 1) > 1 or source.mode == "CMYK":
            return None
        icc = source.info.get("icc_profile")
        image = ImageOps.exif_transpose(source)  # rotation baked in, Orientation tag reset
        exif = image.getexif().tobytes() if image.getexif() else b""
        resized = bool(opts.max_size) and max(image.size) > opts.max_size
        if resized:
            image.thumbnail((opts.max_size, opts.max_size), Image.Resampling.LANCZOS)
        if not resized and content_type == "image/webp":
            return None  # lossy or lossless - can't tell; a WebP is compact already

        has_alpha = "A" in image.getbands() or "transparency" in image.info
        out = io.BytesIO()
        extra: dict = {"icc_profile": icc} if icc else {}
        if exif:
            extra["exif"] = exif
        if opts.webp:
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if has_alpha else "RGB")
            image.save(out, "WEBP", quality=opts.quality, method=6, **extra)
            if content_type == "image/png":
                lossless = io.BytesIO()
                image.save(lossless, "WEBP", lossless=True, quality=100, method=4, **extra)
                if lossless.tell() < out.tell() * PHOTO_RATIO:
                    out = lossless
            result = "image/webp"
        elif content_type == "image/jpeg":
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(out, "JPEG", quality=opts.quality, optimize=True, progressive=True, **extra)
            result = "image/jpeg"
        else:  # PNG, or a resized WebP in «Original» mode - same type, lossless for PNG
            fmt = "PNG" if content_type == "image/png" else "WEBP"
            image.save(out, fmt, optimize=True, quality=opts.quality, **extra)
            result = content_type

    data = out.getvalue()
    limit = len(content) if resized else len(content) * (1 - MIN_GAIN)
    if len(data) >= limit:
        return None
    return Optimized(data, result)


async def optimize_image(
    content: bytes, content_type: str | None, opts: ImageOptions | None = None
) -> Optimized | None:
    """*content* compressed per the site's settings (or *opts*), or None when it
    stays as is (not an image we touch, compression off, nothing gained)."""
    if content_type not in OPTIMIZABLE:
        return None
    opts = opts or await image_options()
    if opts is None:
        return None
    try:
        # Decoding / encoding is CPU work - keep it off the event loop.
        return await asyncio.to_thread(_optimize, content, content_type, opts)
    except Exception as e:  # noqa: BLE001 - a file Pillow can't handle is stored as uploaded
        log.warning("image.optimize_failed", content_type=content_type, error=str(e))
        return None
