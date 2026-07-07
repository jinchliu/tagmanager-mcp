"""Tools for GTM tags: read (list/get) and write (create/update/delete)."""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


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


@mcp.tool(annotations=_WRITE)
async def create_tag(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag: dict[str, Any],
) -> dict[str, Any]:
    """Creates a tag in the workspace draft.

    Changes stay in the workspace until a version is published; nothing
    goes live. Returns the created tag including its tagId.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        tag: Tag resource body. Requires 'name' and 'type'; most types
            also need 'parameter' (list of {'type', 'key', 'value'}
            dicts) and 'firingTriggerId' (list of trigger ID strings).
            Minimal example: {'name': 'Hello', 'type': 'html',
            'parameter': [{'type': 'template', 'key': 'html', 'value':
            '<script>...</script>'}], 'firingTriggerId': ['2147479553']}
            (2147479553 is the built-in All Pages trigger; built-in
            triggers do not appear in list_triggers).
    """
    return await asyncio.to_thread(
        _create_tag_sync, account_id, container_id, workspace_id, tag
    )


def _create_tag_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    return client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .tags()
        .create(parent=parent, body=tag),
        mutating=True,
    )


@mcp.tool(annotations=_WRITE)
async def update_tag(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Updates a tag by merging changes into its current configuration.

    The merge is shallow: each top-level key in changes replaces the
    current value, a null value removes the key, and lists are replaced
    whole (e.g. firingTriggerId must be the complete new list). The
    current config is re-read in the same call and its fingerprint sent
    along, so concurrent edits fail cleanly instead of being clobbered.
    Changes stay in the workspace draft until a version is published.
    Returns the updated tag.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        tag_id: Numeric tag ID; find it via list_tags.
        changes: Partial tag body, e.g. {'paused': True} or
            {'firingTriggerId': ['5', '7']}.
    """
    return await asyncio.to_thread(
        _update_tag_sync,
        account_id,
        container_id,
        workspace_id,
        tag_id,
        changes,
    )


def _update_tag_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'tags', tag_id
    )
    tags_api = service.accounts().containers().workspaces().tags()
    current = client.execute(tags_api.get(path=path))
    kwargs: dict[str, Any] = {
        'path': path,
        'body': utils.merge_patch(current, changes),
    }
    if 'fingerprint' in current:
        kwargs['fingerprint'] = current['fingerprint']
    return client.execute(tags_api.update(**kwargs), mutating=True)


@mcp.tool(annotations=_DESTRUCTIVE)
async def delete_tag(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Deletes a tag from the workspace draft.

    Requires explicit confirmation: ask the user first, then call again
    with confirm=True. The removal stays in the workspace until a
    version is published.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        tag_id: Numeric tag ID; find it via list_tags.
        confirm: Must be True to actually delete.
    """
    if not confirm:
        raise ValueError(
            'Deletion not confirmed. Ask the user to approve deleting'
            f' tag {tag_id}, then call delete_tag with confirm=True.'
        )
    return await asyncio.to_thread(
        _delete_tag_sync, account_id, container_id, workspace_id, tag_id
    )


def _delete_tag_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    tag_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_entity_path(
        account_id, container_id, workspace_id, 'tags', tag_id
    )
    client.execute(
        service.accounts().containers().workspaces().tags().delete(path=path),
        mutating=True,
    )
    return {'deleted': path}
