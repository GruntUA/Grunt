from grunt.api.router import GruntRouter
from grunt.api.v1.docs.crud import router as crud_router

# The generic any-doctype operations (tree, link search, comments, export,
# history, sidebar, workflow) are HTTP methods in grunt.api.v1.document, not
# REST routes. crud_router is the only router here: the 5 base CRUD verbs on
# /docs/{doctype}(/{id}).

router = GruntRouter()

router.include_router(crud_router)
