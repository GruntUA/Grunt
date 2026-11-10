"""Background execution of DocType controller methods via grunt.enqueue_doc()."""

from typing import Any

import grunt
from grunt.auth.users import get_user_by_email
from grunt.log import log
from grunt.site.manager import site_manager
from grunt.tasks.broker import task
from grunt.tasks.enqueue import enqueue
lazy from grunt.document.api import documents


@task
async def _run_doc_method(
    *,
    site: str,
    user_email: str,
    doctype: str,
    doc_id: str,
    method: str,
    kwargs: dict[str, Any],
) -> None:
    """Execute ``doc.<method>(**kwargs)`` in a background worker."""
    maker = site_manager.get_session_maker(site)
    engine = site_manager.get_engine(site)

    async with maker() as session:
        async with grunt.context(session):
            user = await get_user_by_email(user_email)
        if user is None:
            log.error(
                "enqueue_doc.user_not_found", email=user_email, doctype=doctype, doc_id=doc_id
            )
            return

        async with grunt.context(session, engine, user):
            try:
                log.info("enqueue_doc.started", doctype=doctype, doc_id=doc_id, method=method)
                doc = await documents.get_doc_instance(doctype, doc_id)
                handler = getattr(doc, method, None)
                if handler is None:
                    raise AttributeError(f"{doctype} controller has no method '{method}'")
                result = handler(**kwargs)
                if hasattr(result, "__await__"):
                    await result
                log.info("enqueue_doc.finished", doctype=doctype, doc_id=doc_id, method=method)
            except Exception:
                log.exception("enqueue_doc.failed", doctype=doctype, doc_id=doc_id, method=method)
                raise


async def enqueue_doc_method(
    *,
    site: str,
    user_email: str,
    doctype: str,
    doc_id: str,
    method: str,
    kwargs: dict[str, Any],
) -> None:
    """Enqueue :func:`_run_doc_method` via the configured broker - after the
    current transaction commits, so the worker sees the document as saved."""
    enqueue(
        _run_doc_method,
        site=site,
        user_email=user_email,
        doctype=doctype,
        doc_id=doc_id,
        method=method,
        kwargs=kwargs,
    )
