"""Server entry point.

Importing the tool modules below registers their @mcp.tool() functions
on the shared FastMCP instance; keep those imports even though nothing
references them directly.
"""

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import structure  # noqa: F401
from tagmanager_mcp.tools import tags  # noqa: F401
from tagmanager_mcp.tools import triggers  # noqa: F401
from tagmanager_mcp.tools import variables  # noqa: F401


def run_server() -> None:
    """Runs the MCP server over stdio."""
    mcp.run()


if __name__ == '__main__':
    run_server()
