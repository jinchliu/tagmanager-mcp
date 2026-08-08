"""Google Tag Manager MCP server."""

import importlib.metadata


def package_version() -> str:
    """Returns the installed package version, or 'unknown' if absent."""
    try:
        return importlib.metadata.version('tagmanager-mcp')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'
