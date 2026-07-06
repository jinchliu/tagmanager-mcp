"""The single FastMCP instance every tool module registers against."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP('Google Tag Manager MCP Server')
