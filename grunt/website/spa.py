"""The built Desk SPA (``npm run build`` → ``dist/``) in production.

With ``debug`` off there is no Vite dev server: the website catch-all serves
``dist/`` files itself, and ``_spa.html`` pulls the hashed entry tags out of
``dist/index.html`` via the ``spa_assets()`` Jinja global.
"""

from __future__ import annotations

import re
from pathlib import Path

from markupsafe import Markup

from grunt import log

DIST_DIR = Path(__file__).resolve().parent.parent.parent / "dist"  # apps/grunt/dist

# <script type="module" src=…>, <link rel="modulepreload" …>, <link rel="stylesheet" …>
_ASSET_TAG_RE = re.compile(
    r'<script\b[^>]*\btype="module"[^>]*></script>'
    r'|<link\b[^>]*\brel="(?:modulepreload|stylesheet)"[^>]*>'
)

_cache: tuple[float, Markup] | None = None


def spa_assets() -> Markup:
    """Entry ``<script>``/``<link>`` tags of the built SPA (cached per build)."""
    global _cache
    index = DIST_DIR / "index.html"
    try:
        mtime = index.stat().st_mtime
    except OSError:
        log.error("website.spa.not_built", dist=str(DIST_DIR))
        return Markup("")
    if _cache is None or _cache[0] != mtime:
        html = index.read_text(encoding="utf-8")
        # Google Fonts stylesheet lives in _spa.html itself — keep only local assets.
        tags = [t for t in _ASSET_TAG_RE.findall(html) if "://" not in t]
        _cache = (mtime, Markup("\n".join(tags)))
    return _cache[1]


def static_file(root: Path, req_path: str) -> Path | None:
    """``root / req_path`` if it is a file inside *root* (no ``..`` escapes)."""
    if not req_path:
        return None
    try:
        candidate = (root / req_path).resolve()
    except OSError, ValueError:
        return None
    if candidate.is_file() and candidate.is_relative_to(root.resolve()):
        return candidate
    return None
