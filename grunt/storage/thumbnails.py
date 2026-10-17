"""File thumbnails - a small WebP preview for images and PDFs (first page).

Made once, at upload, and stored next to the file (``File.thumbnail_path``);
served by ``get_content(..., thumb=1)`` with the same access rules and signed
URLs as the file itself. Grids (library, file manager) load these instead of
full-size originals, and PDFs finally get a real preview instead of an icon.

PDFs are rendered with pypdfium2 (PDFium, Apache/BSD - no AGPL dependency).
"""

import asyncio
import io

lazy import pypdfium2 as pdfium
lazy from PIL import Image

from grunt import log

THUMB_WIDTH = 480
THUMB_MIMETYPE = "image/webp"
# Wider previews for public pages (``srcset``): made on first request, never upscaled.
WEB_WIDTHS = (THUMB_WIDTH, 960, 1600)

_RASTER_IMAGES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def can_thumbnail(content_type: str | None) -> bool:
    return content_type in _RASTER_IMAGES or content_type == "application/pdf"


def _to_webp(image, width: int) -> bytes:  # PIL.Image.Image

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    image.thumbnail((width, width * 2), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "WEBP", quality=80, method=4)
    return out.getvalue()


def _render(content: bytes, content_type: str, width: int) -> bytes:
    if content_type == "application/pdf":
        pdf = pdfium.PdfDocument(content)
        try:
            page = pdf[0]
            scale = width / page.get_width()
            return _to_webp(page.render(scale=scale).to_pil(), width)
        finally:
            pdf.close()

    with Image.open(io.BytesIO(content)) as image:
        image.seek(0)  # first frame of an animated GIF / WebP
        return _to_webp(image.copy(), width)


async def make_thumbnail(
    content: bytes, content_type: str | None, width: int = THUMB_WIDTH
) -> bytes | None:
    """WebP preview of *content* at most *width* px wide, or None (unsupported
    type or a broken file)."""
    if not can_thumbnail(content_type):
        return None
    try:
        # Decoding / rendering is CPU work - keep it off the event loop.
        return await asyncio.to_thread(_render, content, content_type or "", width)
    except Exception as e:  # noqa: BLE001 - a bad file just goes without a preview
        log.warning("thumbnail.failed", content_type=content_type, error=str(e))
        return None
