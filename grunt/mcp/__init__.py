"""Model Context Protocol server - lets AI agents work with Grunt data.

Exposed at ``/api/v1/mcp`` (Streamable HTTP). Authenticate with an API key
(``X-Api-Key``) or a bearer token; tools act as that user.
"""

from grunt.mcp import tools as _core_tools  # noqa: F401  (registers core tools)
from grunt.mcp.registry import McpTool, get_tool, list_tools, mcp_tool, register_tool

__all__ = ["McpTool", "get_tool", "list_tools", "mcp_tool", "register_tool"]
