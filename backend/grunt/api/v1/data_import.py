from fastapi import BackgroundTasks, Depends

from grunt.app import grunt
from grunt.api.router import GruntRouter

router = GruntRouter(prefix="", tags=["data_import"])


@router.get("/preview/{data_import_id}")
async def get_import_preview(
    data_import_id: str,
):
    di_doc = await grunt.get_doc("DataImport", data_import_id)
    return await di_doc.get_preview()


@router.post("/run/{data_import_id}")
async def run_import(
    data_import_id: str,
    background_tasks: BackgroundTasks,
):
    di_doc = await grunt.get_doc("DataImport", data_import_id)

    # Run in background
    background_tasks.add_task(di_doc.run)

    return {"message": "Import started in background", "id": data_import_id}
