from grunt.api.router import GruntRouter
from grunt.api.v1.docs.collaboration import router as collaboration_router
from grunt.api.v1.docs.crud import router as crud_router
from grunt.api.v1.docs.export import router as export_router
from grunt.api.v1.docs.history import router as history_router
from grunt.api.v1.docs.link import router as link_router
from grunt.api.v1.docs.meta import router as meta_router
from grunt.api.v1.docs.tree import router as tree_router
from grunt.api.v1.docs.workflow import router as workflow_router

router = GruntRouter()

# Include sub-routers.  Order matters: more specific paths FIRST so they are
# not shadowed by the generic /{doctype}/{doc_id} patterns in crud_router.

router.include_router(tree_router)  # /{doctype}/tree/...
router.include_router(link_router)  # /{doctype}/link_search
router.include_router(workflow_router)
router.include_router(export_router)
router.include_router(history_router)
router.include_router(collaboration_router)
router.include_router(meta_router)
router.include_router(crud_router)
