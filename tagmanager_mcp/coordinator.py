"""The single MCPServer instance every tool module registers against."""

from mcp.server.mcpserver import MCPServer

from tagmanager_mcp import package_version

mcp = MCPServer('Google Tag Manager MCP Server', version=package_version())
