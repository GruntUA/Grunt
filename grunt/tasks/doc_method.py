"""Background execution of DocType controller methods via grunt.enqueue_doc()."""

from __future__ import annotations

from typing import Any

from grunt import log
from grunt.site.manager import site_manager
from grunt.tasks.broker import task


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
    import grunt
    from grunt.auth.doctypes.User.user import get_user_by_email

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
                doc = await grunt.get_doc_instance(doctype, doc_id)
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
    """Enqueue :func:`_run_doc_method` via the configured broker."""
    await _run_doc_method.kiq(
        site=site,
        user_email=user_email,
        doctype=doctype,
        doc_id=doc_id,
        method=method,
        kwargs=kwargs,
    )
