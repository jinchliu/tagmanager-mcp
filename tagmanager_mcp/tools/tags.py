"""Read-only tools for GTM tags."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def list_tags(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    """Lists tags in a workspace, skeleton fields only.

    Returns tagId, name, type, firingTriggerId, blockingTriggerId,
    paused and fingerprint per tag. Use get_tag for the full
    configuration of a specific tag.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
    """
    return await asyncio.to_thread(
        _list_tags_sync, account_id, container_id, workspace_id
    )


def _list_tags_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    tags = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .workspaces()
        .tags()
        .list(parent=parent, pageToken=token),
        'tag',
    )
    return {'tags': [utils.slim_tag(tag) for tag in tags]}


@mcp.tool(annotations=_READ_ONLY)
async def get_tag(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
) -> dict[str, Any]:
    """Gets the full configuration of one tag, including parameters.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        tag_id: Numeric tag ID; find it via list_tags.
    """
    return await asyncio.to_thread(
        _get_tag_sync, account_id, container_id, workspace_id, tag_id
    )


def _get_tag_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'tags', tag_id
    )
    return client.execute(
        service.accounts().containers().workspaces().tags().get(path=path)
    )
