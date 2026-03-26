"""Translations API — serves PO-based translations as JSON for the frontend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from grunt.core.i18n import translation_service

router = APIRouter(prefix="/translations", tags=["i18n"])


@router.get("/{locale}")
async def get_translations(locale: str) -> dict[str, Any]:
    """Return all translations for a locale as a flat JSON dict.

    Used by the frontend to load translations from PO source of truth.
    """
    translations = translation_service.get_all_translations(locale)
    return {"success": True, "data": translations}
