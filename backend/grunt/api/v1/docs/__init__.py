from grunt.api.router import GruntRouter

from grunt.api.v1.docs.collaboration import router as collaboration_router
from grunt.api.v1.docs.crud import router as crud_router
from grunt.api.v1.docs.export import router as export_router
from grunt.api.v1.docs.history import router as history_router
from grunt.api.v1.docs.meta import router as meta_router
from grunt.api.v1.docs.workflow import router as workflow_router

router = GruntRouter()

# Include sub-routers.  Order may matter if there are overlapping patterns,
# but our paths are fairly distinct (except /doctype/doc_id/action).
# Actually, crud has /{doctype} and /{doctype}/{doc_id}. So we should include
# more specific paths FIRST.

router.include_router(workflow_router)
router.include_router(export_router)
router.include_router(history_router)
router.include_router(collaboration_router)
router.include_router(meta_router)
router.include_router(crud_router)
