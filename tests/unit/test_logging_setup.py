"""Console logging: uvicorn's WebSocket handshake lines are dropped, the log
facade resolves the calling module cheaply, and re-configuring replaces the
console handler instead of stacking a second one."""

from __future__ import annotations

import logging
import sys

import io

from sqlalchemy.exc import OperationalError

from grunt.logging_config import (
    _HandledExceptionFilter,
    _WebSocketHandshakeFilter,
    compact_exception_formatter,
    configure_console_logging,
    mark_logged,
)


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, msg, args, None)


def test_websocket_handshake_lines_are_dropped() -> None:
    f = _WebSocketHandshakeFilter()
    assert not f.filter(_record('%s - "WebSocket %s" [accepted]', "1.2.3.4:0", "/api/v1/ws/user"))
    assert not f.filter(_record('%s - "WebSocket %s" 403', "1.2.3.4:0", "/api/v1/ws/user"))
    assert not f.filter(_record("connection open"))
    assert not f.filter(_record("connection closed"))
    assert not f.filter(_record("connection rejected (%d %s)", 403, "Forbidden"))
    assert f.filter(_record("Application startup complete."))


def test_caller_module_is_the_logging_module() -> None:
    log_module = sys.modules["grunt.log"]

    def emit() -> str:
        return log_module._caller_module(1)

    assert emit() == __name__


def test_reconfigure_keeps_one_console_handler() -> None:
    root = logging.getLogger()
    configure_console_logging("INFO")
    before = len(root.handlers)
    configure_console_logging("WARNING")
    assert len(root.handlers) == before
    configure_console_logging("INFO")


def _raise_db_error() -> None:
    statement = "SELECT " + ", ".join(f"col_{i}" for i in range(200)) + " FROM t"
    raise OperationalError(statement, (1, "x" * 50), Exception("database or disk is full"))


def test_compact_traceback_is_short_and_names_the_cause() -> None:
    try:
        _raise_db_error()
    except OperationalError as e:
        exc_info = (type(e), e, e.__traceback__)
    out = io.StringIO()
    compact_exception_formatter(out, exc_info)
    text = out.getvalue()

    assert "OperationalError: database or disk is full" in text
    assert "  SQL: SELECT col_0" in text and text.rstrip().endswith("…")
    assert "in _raise_db_error" in text  # project frame kept
    assert "locals" not in text
    assert len(text.splitlines()) < 12


def test_already_logged_500_is_not_printed_again_by_uvicorn() -> None:
    exc = RuntimeError("boom")
    record = _record("Exception in ASGI application\n")
    record.exc_info = (RuntimeError, exc, None)
    f = _HandledExceptionFilter()
    assert f.filter(record)
    mark_logged(exc)
    assert not f.filter(record)
