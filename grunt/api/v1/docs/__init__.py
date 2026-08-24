from grunt.api.router import GruntRouter
from grunt.api.v1.docs.crud import router as crud_router

# NOTE: tree.py, link.py, collaboration.py, export.py, history.py, meta.py and
# workflow.py used to live here as RPC-only whitelisted-method modules; they
# were generic (any-doctype) operations, not REST routes, so they moved to
# grunt/document/mixins/*_rpc.py and are now static methods of the base
# `Document` controller (grunt.document.base.Document.<method>), dispatched
# via /api/v1/method/... same as before. crud_router is the only router left
# here: the 5 base CRUD verbs on /docs/{doctype}(/{id}).

router = GruntRouter()

router.include_router(crud_router)
