"""Scripting module — Server Script (Python) and Client Script (JS) engine."""

from grunt.core.scripting.server_script import ServerScriptRunner

server_script_runner = ServerScriptRunner()

__all__ = ["server_script_runner", "ServerScriptRunner"]
