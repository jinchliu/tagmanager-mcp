"""Read-only tools for the GTM account/container/workspace hierarchy."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def list_accounts(
    include_google_tags: bool = False,
) -> dict[str, Any]:
    """Lists all Google Tag Manager accounts accessible to the caller.

    Args:
        include_google_tags: Also include Google Tag accounts in the
            results.
    """
    return await asyncio.to_thread(_list_accounts_sync, include_google_tags)


def _list_accounts_sync(include_google_tags: bool) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    accounts = utils.paginate(
        lambda token: service.accounts().list(
            includeGoogleTags=include_google_tags, pageToken=token
        ),
        'account',
    )
    return {'accounts': accounts}


@mcp.tool(annotations=_READ_ONLY)
async def list_containers(account_id: int | str) -> dict[str, Any]:
    """Lists all containers in a Google Tag Manager account.

    Args:
        account_id: Numeric GTM account ID (e.g. 6000000000) or a full
            path like 'accounts/6000000000'.
    """
    return await asyncio.to_thread(_list_containers_sync, account_id)


def _list_containers_sync(account_id: int | str) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_account_path(account_id)
    containers = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .list(parent=parent, pageToken=token),
        'container',
    )
    return {'containers': containers}


@mcp.tool(annotations=_READ_ONLY)
async def list_workspaces(
    account_id: int | str, container_id: int | str
) -> dict[str, Any]:
    """Lists workspaces in a container.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID (e.g. 200001) or a full path
            like 'accounts/123/containers/200001'.
    """
    return await asyncio.to_thread(
        _list_workspaces_sync, account_id, container_id
    )


def _list_workspaces_sync(
    account_id: int | str, container_id: int | str
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_container_path(account_id, container_id)
    workspaces = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .workspaces()
        .list(parent=parent, pageToken=token),
        'workspace',
    )
    return {'workspaces': workspaces}


@mcp.tool(annotations=_READ_ONLY)
async def get_workspace_status(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    """Shows unpublished changes and merge conflicts in a workspace.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
    """
    return await asyncio.to_thread(
        _get_workspace_status_sync, account_id, container_id, workspace_id
    )


def _get_workspace_status_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    response = client.execute(
        service.accounts().containers().workspaces().getStatus(path=path)
    )
    return {
        'workspaceChange': response.get('workspaceChange', []),
        'mergeConflict': response.get('mergeConflict', []),
    }
