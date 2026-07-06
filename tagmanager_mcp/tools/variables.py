"""Read-only tools for GTM variables."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def list_variables(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    """Lists variables in a workspace, skeleton fields only.

    Returns variableId, name, type and fingerprint per variable. Use
    get_variable for the full configuration of a specific variable.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
    """
    return await asyncio.to_thread(
        _list_variables_sync, account_id, container_id, workspace_id
    )


def _list_variables_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    variables = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .workspaces()
        .variables()
        .list(parent=parent, pageToken=token),
        'variable',
    )
    return {
        'variables': [utils.slim_variable(variable) for variable in variables]
    }


@mcp.tool(annotations=_READ_ONLY)
async def get_variable(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
) -> dict[str, Any]:
    """Gets the full configuration of one variable.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        variable_id: Numeric variable ID; find it via list_variables.
    """
    return await asyncio.to_thread(
        _get_variable_sync,
        account_id,
        container_id,
        workspace_id,
        variable_id,
    )


def _get_variable_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'variables', variable_id
    )
    return client.execute(
        service.accounts().containers().workspaces().variables().get(path=path)
    )
