"""Tools for GTM triggers: read (list/get) and write (create/update/delete)."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


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


@mcp.tool(annotations=_WRITE)
async def create_trigger(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger: dict[str, Any],
) -> dict[str, Any]:
    """Creates a trigger in the workspace draft.

    Changes stay in the workspace until a version is published; nothing
    goes live. Returns the created trigger including its triggerId.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        trigger: Trigger resource body. Requires 'name' and 'type'
            (e.g. 'pageview', 'domReady', 'click', 'customEvent').
            Minimal example: {'name': 'DOM Ready', 'type': 'domReady'}.
            A customEvent trigger also needs 'customEventFilter', e.g.
            [{'type': 'equals', 'parameter': [{'type': 'template',
            'key': 'arg0', 'value': '{{_event}}'}, {'type': 'template',
            'key': 'arg1', 'value': 'my_event'}]}].
    """
    return await asyncio.to_thread(
        _create_trigger_sync, account_id, container_id, workspace_id, trigger
    )


def _create_trigger_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    return client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .triggers()
        .create(parent=parent, body=trigger),
        mutating=True,
    )


@mcp.tool(annotations=_WRITE)
async def update_trigger(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Updates a trigger by merging changes into its current config.

    The merge is shallow: each top-level key in changes replaces the
    current value, a null value removes the key, and lists are replaced
    whole (e.g. a filter list must be passed complete). The current
    config is re-read in the same call and its fingerprint sent along,
    so concurrent edits fail cleanly instead of being clobbered.
    Changes stay in the workspace draft until a version is published.
    Returns the updated trigger.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        trigger_id: Numeric trigger ID; find it via list_triggers.
        changes: Partial trigger body, e.g. {'name': 'New name'}.
    """
    return await asyncio.to_thread(
        _update_trigger_sync,
        account_id,
        container_id,
        workspace_id,
        trigger_id,
        changes,
    )


def _update_trigger_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'triggers', trigger_id
    )
    triggers_api = service.accounts().containers().workspaces().triggers()
    current = client.execute(triggers_api.get(path=path))
    kwargs: dict[str, Any] = {
        'path': path,
        'body': utils.merge_patch(current, changes),
    }
    if 'fingerprint' in current:
        kwargs['fingerprint'] = current['fingerprint']
    return client.execute(triggers_api.update(**kwargs), mutating=True)


@mcp.tool(annotations=_DESTRUCTIVE)
async def delete_trigger(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Deletes a trigger from the workspace draft.

    Requires explicit confirmation: ask the user first, then call again
    with confirm=True. Check first (via list_tags) that no tag still
    references the trigger. The removal stays in the workspace until a
    version is published.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        trigger_id: Numeric trigger ID; find it via list_triggers.
        confirm: Must be True to actually delete.
    """
    if not confirm:
        raise ValueError(
            'Deletion not confirmed. Ask the user to approve deleting'
            f' trigger {trigger_id}, then call delete_trigger with'
            ' confirm=True.'
        )
    return await asyncio.to_thread(
        _delete_trigger_sync,
        account_id,
        container_id,
        workspace_id,
        trigger_id,
    )


def _delete_trigger_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    trigger_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'triggers', trigger_id
    )
    client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .triggers()
        .delete(path=path),
        mutating=True,
    )
    return {'deleted': path}
