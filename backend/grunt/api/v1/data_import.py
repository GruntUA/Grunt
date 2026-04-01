from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any
from pathlib import Path

from grunt.core.auth.dependencies import current_user, get_session
from grunt.core.auth.models import GruntUser
from grunt.core.document.service import DocumentService
from grunt.core.document.registry import document_registry
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/preview/{data_import_id}")
async def get_import_preview(
    data_import_id: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session)
):
    doc_service = DocumentService(session)
    # Get raw data
    di_raw = await doc_service.get_document("DataImport", data_import_id, user)
    # Get controller
    controller_cls = document_registry.get("DataImport")
    di_doc = controller_cls("DataImport", di_raw, user, session)
    
    return await di_doc.get_preview()

@router.post("/run/{data_import_id}")
async def run_import(
    data_import_id: str,
    background_tasks: BackgroundTasks,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session)
):
    doc_service = DocumentService(session)
    di_raw = await doc_service.get_document("DataImport", data_import_id, user)
    controller_cls = document_registry.get("DataImport")
    di_doc = controller_cls("DataImport", di_raw, user, session)
    
    # Run in background
    background_tasks.add_task(di_doc.run)
    
    return {"message": "Import started in background", "id": data_import_id}
