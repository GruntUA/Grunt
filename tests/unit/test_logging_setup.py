"""Console logging: uvicorn's WebSocket handshake lines are dropped, the log
facade resolves the calling module cheaply, and re-configuring replaces the
console handler instead of stacking a second one."""

from __future__ import annotations

import logging
import sys

from grunt.logging_config import _WebSocketHandshakeFilter, configure_console_logging


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, msg, args, None)


def test_websocket_handshake_lines_are_dropped() -> None:
    f = _WebSocketHandshakeFilter()
    assert not f.filter(_record('%s - "WebSocket %s" [accepted]', "1.2.3.4:0", "/api/v1/ws/user"))
    assert not f.filter(_record('%s - "WebSocket %s" 403', "1.2.3.4:0", "/api/v1/ws/user"))
    assert not f.filter(_record("connection open"))
    assert not f.filter(_record("connection closed"))
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
