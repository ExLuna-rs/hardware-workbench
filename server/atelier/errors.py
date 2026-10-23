"""Erreurs dont le message est renvoyé tel quel à Claude (les autres sont masquées par le SDK MCP)."""

from mcp.server.mcpserver.exceptions import ToolError


class AtelierError(ToolError):
    pass
