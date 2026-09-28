"""HTML → PDF rendering via headless Chromium (Playwright).

One predictable rendering path for every "print to PDF" feature — the document
print RPC and any app-level PDF (e.g. correspondence letters). Unlike
WeasyPrint, output does not depend on the host's Pango / cairo / fontconfig
versions: the only moving parts are the pinned ``playwright`` package and the
Chromium build it manages (``playwright install chromium``).

The input HTML must be self-contained (inline CSS, ``data:`` URIs) — no network
load is awaited beyond ``load``. ``@page`` rules in the document drive the page
size; page margins are forced to zero so the template's own padding is the
single source of whitespace.
"""

from __future__ import annotations

_INSTALL_HINT = (
    "PDF generation is unavailable: Playwright / Chromium or its system libraries "
    "are not installed. Run `pip install playwright`, `playwright install chromium` "
    "and, on a server (as root), `playwright install-deps chromium`."
)


class PdfEngineError(RuntimeError):
    """Playwright or its Chromium build is not installed."""


async def html_to_pdf(html: str) -> bytes:
    """Render a self-contained HTML string to PDF bytes with headless Chromium.

    Raises :class:`PdfEngineError` when Playwright or Chromium is missing;
    any other rendering error propagates unchanged.
    """
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
        raise PdfEngineError(_INSTALL_HINT) from exc

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=["--no-sandbox"])
            try:
                page = await browser.new_page()
                await page.emulate_media(media="print")
                await page.set_content(html, wait_until="load")
                return await page.pdf(
                    format="A4",
                    prefer_css_page_size=True,
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
            finally:
                await browser.close()
    except PlaywrightError as exc:
        msg = str(exc).lower()
        if (
            "executable doesn't exist" in msg
            or "error while loading shared libraries" in msg
            or "host system is missing dependencies" in msg
        ):
            raise PdfEngineError(_INSTALL_HINT) from exc
        raise
