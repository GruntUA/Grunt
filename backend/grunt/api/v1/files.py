"""File upload / download API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.config import settings
from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session
from grunt.core.db.system_tables import GruntFile
from grunt.core.storage import get_storage_backend

router = APIRouter()

MAX_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("")
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
            f"File too large (max {settings.max_upload_size_mb} MB)",
        )

    content_type = file.content_type or "application/octet-stream"

    storage = get_storage_backend()
    try:
        path = await storage.save(
            content=content,
            filename=file.filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from exc

    record = GruntFile(
        filename=path.split("/")[-1],
        original_name=file.filename,
        content_type=content_type,
        size_bytes=len(content),
        path=path,
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


@router.get("")
async def list_files(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """List uploaded files with pagination and search."""
    stmt = select(GruntFile).order_by(GruntFile.created_at.desc())
    if search:
        stmt = stmt.where(GruntFile.original_name.ilike(f"%{search}%"))
    
    stmt = stmt.offset(offset).limit(limit)
    result = await session.execute(stmt)
    records = result.scalars().all()
    
    # Get total count
    from sqlalchemy import func  # noqa: PLC0415
    count_stmt = select(func.count()).select_from(GruntFile)
    if search:
        count_stmt = count_stmt.where(GruntFile.original_name.ilike(f"%{search}%"))
    total = await session.scalar(count_stmt) or 0
    
    data = [
        {
            "id": r.id,
            "url": f"/api/v1/files/{r.id}",
            "filename": r.original_name,
            "content_type": r.content_type,
            "size_bytes": r.size_bytes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "uploaded_by": r.uploaded_by,
        }
        for r in records
    ]
    
    return {
        "success": True,
        "data": data,
        "total": total,
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
        raise HTTPException(404, "File not found")

    storage = get_storage_backend()
    try:
        content = await storage.get(record.path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found on storage")

    return Response(
        content=content,
        media_type=record.content_type,
        headers={"Content-Disposition": f'attachment; filename="{record.original_name}"'},
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
        raise HTTPException(404, "File not found")

    storage = get_storage_backend()
    await storage.delete(record.path)

    await session.delete(record)
    await session.commit()

    return {"success": True, "data": {"id": file_id}}
