"""Persist unhandled errors to the ``ErrorLog`` DocType.

The single write path for the error journal. Everything here is *best-effort*:
a failure to record an error must never mask or replace the original error, so
every public function swallows its own exceptions and logs a warning instead.

Callers:

* :func:`grunt.startup.errors._generic_exception` — unhandled HTTP 500s;
* :mod:`grunt.tasks.middleware` — background-task failures that won't retry;
* application code via :func:`grunt.log_error` (see ``grunt/__init__.py``).
"""

from __future__ import annotations

import traceback as _tb
from typing import TYPE_CHECKING, Any

from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_TITLE_MAX = 200
_MESSAGE_MAX = 8000
_TRACEBACK_MAX = 16000


def _app_of_traceback(tb_text: str) -> str:
    """Best-effort: name the app whose frame is deepest in the traceback.

    ``grunt`` for framework code, otherwise the top-level package of the last
    ``bench/apps/<app>/...`` frame (``hrm``, ``car_ua``, ...).
    """
    app = "grunt"
    for line in tb_text.splitlines():
        line = line.strip()
        if not line.startswith('File "'):
            continue
        path = line.split('"', 2)[1]
        parts = path.replace("\\", "/").split("/")
        if "apps" in parts:
            idx = parts.index("apps")
            if idx + 1 < len(parts):
                app = parts[idx + 1]
        elif "site-packages" in parts or "grunt" in parts:
            app = "grunt"
    return app


def _clip(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _write_row(payload: dict[str, Any], session: AsyncSession | None) -> str | None:
    """Insert one ErrorLog row, either on *session* or a fresh isolated one."""
    from grunt.app import grunt

    if session is not None:
        # Caller owns the transaction (e.g. the task middleware already holds a
        # system_context). Reuse it so the row commits with the caller's work.
        doc = await grunt.new_doc("ErrorLog", payload)
        return doc.get("name")

    # HTTP path: the request's own session is very likely in a failed
    # transaction by now, so open a fresh one bound to the active site.
    from grunt.site.manager import site_manager

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as fresh, grunt.system_context(fresh, eng):
        doc = await grunt.new_doc("ErrorLog", payload)
        await fresh.commit()
        return doc.get("name")


async def record_error(
    *,
    exc: BaseException | None = None,
    title: str | None = None,
    message: str | None = None,
    context: str = "Manual",
    method: str | None = None,
    user: str | None = None,
    app: str | None = None,
    http_status: int | None = None,
    request_method: str | None = None,
    request_path: str | None = None,
    request_id: str | None = None,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    session: AsyncSession | None = None,
) -> str | None:
    """Write one ``ErrorLog`` row. Returns its id, or ``None`` on any failure.

    Pass ``exc`` to capture its type, message and traceback automatically, or
    ``title`` / ``message`` explicitly. Never raises.
    """
    try:
        tb_text = ""
        error_type = ""
        if exc is not None:
            error_type = type(exc).__name__
            tb_text = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
            message = message or str(exc)
        else:
            tb_text = _tb.format_exc()
            if tb_text.strip() == "NoneType: None":
                tb_text = ""

        if not title:
            title = f"{error_type}: {message}" if error_type else (message or "Error")

        if app is None and tb_text:
            app = _app_of_traceback(tb_text)

        if user is None:
            try:
                from grunt.app import grunt

                user = grunt.get_user().email
            except Exception:
                user = None

        payload: dict[str, Any] = {
            "title": _clip(title, _TITLE_MAX),
            "error_type": error_type or None,
            "context": context,
            "method": method,
            "user": user,
            "app": app,
            "http_status": http_status,
            "request_method": request_method,
            "request_path": request_path,
            "request_id": request_id,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "error_message": _clip(message, _MESSAGE_MAX) or None,
            "traceback": _clip(tb_text, _TRACEBACK_MAX) or None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        return await _write_row(payload, session)
    except Exception as log_exc:  # noqa: BLE001 — logging must never raise
        log.warning("error_log.write_failed", error=str(log_exc))
        return None
