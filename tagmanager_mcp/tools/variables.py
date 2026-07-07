"""Tools for GTM variables: read (list/get) and write (create/update/delete)."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


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


@mcp.tool(annotations=_WRITE)
async def create_variable(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable: dict[str, Any],
) -> dict[str, Any]:
    """Creates a variable in the workspace draft.

    Changes stay in the workspace until a version is published; nothing
    goes live. Returns the created variable including its variableId.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        variable: Variable resource body. Requires 'name' and 'type';
            most types also need 'parameter' (list of {'type', 'key',
            'value'} dicts). Data layer variable example: {'name':
            'DL - user_id', 'type': 'v', 'parameter': [{'type':
            'integer', 'key': 'dataLayerVersion', 'value': '2'},
            {'type': 'template', 'key': 'name', 'value': 'user_id'}]}.
    """
    return await asyncio.to_thread(
        _create_variable_sync,
        account_id,
        container_id,
        workspace_id,
        variable,
    )


def _create_variable_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    return client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .variables()
        .create(parent=parent, body=variable),
        mutating=True,
    )


@mcp.tool(annotations=_WRITE)
async def update_variable(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Updates a variable by merging changes into its current config.

    The merge is shallow: each top-level key in changes replaces the
    current value, a null value removes the key, and lists are replaced
    whole (e.g. the parameter list must be passed complete). The
    current config is re-read in the same call and its fingerprint sent
    along, so concurrent edits fail cleanly instead of being clobbered.
    Changes stay in the workspace draft until a version is published.
    Returns the updated variable.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        variable_id: Numeric variable ID; find it via list_variables.
        changes: Partial variable body, e.g. {'name': 'New name'}.
    """
    return await asyncio.to_thread(
        _update_variable_sync,
        account_id,
        container_id,
        workspace_id,
        variable_id,
        changes,
    )


def _update_variable_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'variables', variable_id
    )
    variables_api = service.accounts().containers().workspaces().variables()
    current = client.execute(variables_api.get(path=path))
    kwargs: dict[str, Any] = {
        'path': path,
        'body': utils.merge_patch(current, changes),
    }
    if 'fingerprint' in current:
        kwargs['fingerprint'] = current['fingerprint']
    return client.execute(variables_api.update(**kwargs), mutating=True)


@mcp.tool(annotations=_DESTRUCTIVE)
async def delete_variable(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Deletes a variable from the workspace draft.

    Requires explicit confirmation: ask the user first, then call again
    with confirm=True. Check first that no tag, trigger or variable
    still references it as {{Variable Name}}. The removal stays in the
    workspace until a version is published.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        variable_id: Numeric variable ID; find it via list_variables.
        confirm: Must be True to actually delete.
    """
    if not confirm:
        raise ValueError(
            'Deletion not confirmed. Ask the user to approve deleting'
            f' variable {variable_id}, then call delete_variable with'
            ' confirm=True.'
        )
    return await asyncio.to_thread(
        _delete_variable_sync,
        account_id,
        container_id,
        workspace_id,
        variable_id,
    )


def _delete_variable_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    variable_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'variables', variable_id
    )
    client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .variables()
        .delete(path=path),
        mutating=True,
    )
    return {'deleted': path}
