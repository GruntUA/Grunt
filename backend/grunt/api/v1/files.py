"""File upload / download API."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntFile

router = APIRouter()

UPLOAD_DIR = Path(settings.upload_dir)
MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/")
async def upload_file(
    file: UploadFile,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Upload a file and return its metadata + URL."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            413,
            f"Файл занадто великий (макс. {settings.max_upload_size_mb} МБ)",
        )

    # Generate unique filename preserving extension
    ext = Path(file.filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"

    # Organize by date: uploads/2026/03/
    from datetime import date

    today = date.today()
    rel_dir = Path(str(today.year)) / f"{today.month:02d}"
    abs_dir = UPLOAD_DIR / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    file_path = abs_dir / unique_name
    file_path.write_bytes(content)

    # Relative path for DB (from upload root)
    rel_path = str(rel_dir / unique_name)

    # Save metadata
    record = GruntFile(
        filename=unique_name,
        original_name=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        path=rel_path,
        uploaded_by=user.email,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return {
        "success": True,
        "data": {
            "id": record.id,
            "url": f"/api/v1/files/{record.id}",
            "filename": record.original_name,
            "content_type": record.content_type,
            "size_bytes": record.size_bytes,
        },
    }


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Download / serve a file by ID."""
    result = await session.execute(
        select(GruntFile).where(GruntFile.id == file_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(404, "Файл не знайдено")

    file_path = UPLOAD_DIR / record.path
    if not file_path.exists():
        raise HTTPException(404, "Файл не знайдено на диску")

    from fastapi.responses import FileResponse

    return FileResponse(
        path=str(file_path),
        media_type=record.content_type,
        filename=record.original_name,
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a file."""
    result = await session.execute(
        select(GruntFile).where(GruntFile.id == file_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(404, "Файл не знайдено")

    # Remove from disk
    file_path = UPLOAD_DIR / record.path
    if file_path.exists():
        file_path.unlink()

    await session.delete(record)
    await session.commit()

    return {"success": True, "data": {"id": file_id}}
