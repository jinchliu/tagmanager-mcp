"""Read-only tools for GTM triggers."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def list_triggers(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    """Lists triggers in a workspace, skeleton fields only.

    Returns triggerId, name, type and fingerprint per trigger. Use
    get_trigger for the full configuration of a specific trigger.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
    """
    return await asyncio.to_thread(
        _list_triggers_sync, account_id, container_id, workspace_id
    )


def _list_triggers_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    triggers = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .workspaces()
        .triggers()
        .list(parent=parent, pageToken=token),
        'trigger',
    )
    return {'triggers': [utils.slim_trigger(trigger) for trigger in triggers]}


@mcp.tool(annotations=_READ_ONLY)
async def get_trigger(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
) -> dict[str, Any]:
    """Gets the full configuration of one trigger, including filters.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        trigger_id: Numeric trigger ID; find it via list_triggers.
    """
    return await asyncio.to_thread(
        _get_trigger_sync, account_id, container_id, workspace_id, trigger_id
    )


def _get_trigger_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'triggers', trigger_id
    )
    return client.execute(
        service.accounts().containers().workspaces().triggers().get(path=path)
    )
