"""Tools for GTM container versions: read (list/get/live) and publish.

Versions are the unit of release. Creating one snapshots a workspace and
consumes it; publishing one pushes it live to the container. These sit in
a separate module to underline that workspace editing is not the same as
going live.
"""

import asyncio
from typing import Any

from mcp.types import ToolAnnotations

from tagmanager_mcp.coordinator import mcp
from tagmanager_mcp.tools import client, utils

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


@mcp.tool(annotations=_READ_ONLY)
async def list_versions(
    account_id: int | str,
    container_id: int | str,
) -> dict[str, Any]:
    """Lists container version headers, skeleton fields only.

    Returns containerVersionId, name, deleted and entity counts per
    version. Use get_version for the full contents of one version, or
    get_live_version for the one currently published.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
    """
    return await asyncio.to_thread(
        _list_versions_sync, account_id, container_id
    )


def _list_versions_sync(
    account_id: int | str,
    container_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_container_path(account_id, container_id)
    headers = utils.paginate(
        lambda token: service.accounts()
        .containers()
        .version_headers()
        .list(parent=parent, pageToken=token),
        'containerVersionHeader',
    )
    return {'versions': [utils.slim_version_header(h) for h in headers]}


@mcp.tool(annotations=_READ_ONLY)
async def get_version(
    account_id: int | str,
    container_id: int | str,
    version_id: int | str,
) -> dict[str, Any]:
    """Gets one container version: metadata plus slimmed contents.

    The embedded tags, triggers and variables are reduced to their
    skeleton (name + id); a full version can otherwise run to thousands
    of lines. Use get_tag/get_trigger/get_variable for full entity
    configs, but note those read the workspace draft, not this version.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        version_id: Numeric version ID; find it via list_versions.
    """
    return await asyncio.to_thread(
        _get_version_sync, account_id, container_id, version_id
    )


def _get_version_sync(
    account_id: int | str,
    container_id: int | str,
    version_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_version_path(account_id, container_id, version_id)
    version = client.execute(
        service.accounts().containers().versions().get(path=path)
    )
    return utils.slim_container_version(version)


@mcp.tool(annotations=_READ_ONLY)
async def get_live_version(
    account_id: int | str,
    container_id: int | str,
) -> dict[str, Any]:
    """Gets the container version currently published (live).

    Returns metadata plus slimmed contents, like get_version. Useful to
    see what is live before publishing a new version.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
    """
    return await asyncio.to_thread(
        _get_live_version_sync, account_id, container_id
    )


def _get_live_version_sync(
    account_id: int | str,
    container_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    parent = utils.construct_container_path(account_id, container_id)
    version = client.execute(
        service.accounts().containers().versions().live(parent=parent)
    )
    return utils.slim_container_version(version)


@mcp.tool(annotations=_DESTRUCTIVE)
async def create_version(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    name: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Snapshots a workspace into a new container version.

    WARNING: this consumes the workspace. The workspace is deleted and a
    fresh empty one is created; its path is returned as newWorkspacePath.
    Use that path for any further edits — the workspace_id passed here is
    gone afterwards. Nothing goes live yet; publish_version does that.

    Check the result before publishing: if compilerError is true or
    syncStatus reports a conflict, the version has problems. Fix them in
    the new workspace and create another version rather than publishing.

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        workspace_id: Numeric workspace ID; find it via list_workspaces.
        name: Optional name for the version.
        notes: Optional notes describing the version.
    """
    return await asyncio.to_thread(
        _create_version_sync,
        account_id,
        container_id,
        workspace_id,
        name,
        notes,
    )


def _create_version_sync(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    name: str | None,
    notes: str | None,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_workspace_path(
        account_id, container_id, workspace_id
    )
    body: dict[str, Any] = {}
    if name is not None:
        body['name'] = name
    if notes is not None:
        body['notes'] = notes
    response = client.execute(
        service.accounts()
        .containers()
        .workspaces()
        .create_version(path=path, body=body),
        mutating=True,
    )
    version = response.get('containerVersion', {})
    return {
        'containerVersionId': version.get('containerVersionId'),
        'newWorkspacePath': response.get('newWorkspacePath'),
        'compilerError': response.get('compilerError', False),
        'syncStatus': response.get('syncStatus', {}),
        'containerVersion': utils.slim_container_version(version),
    }


@mcp.tool(annotations=_DESTRUCTIVE)
async def publish_version(
    account_id: int | str,
    container_id: int | str,
    version_id: int | str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Publishes a container version, making it live on the site.

    This is the only operation that changes what runs on the live site.
    Requires explicit confirmation: ask the user first, then call again
    with confirm=True. Publish a version you have already checked for
    compiler errors (see create_version).

    Args:
        account_id: Numeric account ID or full resource path.
        container_id: Numeric container ID or full resource path.
        version_id: Numeric version ID; find it via list_versions.
        confirm: Must be True to actually publish.
    """
    if not confirm:
        raise ValueError(
            'Publish not confirmed. Ask the user to approve publishing'
            f' version {version_id} live, then call publish_version with'
            ' confirm=True.'
        )
    return await asyncio.to_thread(
        _publish_version_sync, account_id, container_id, version_id
    )


def _publish_version_sync(
    account_id: int | str,
    container_id: int | str,
    version_id: int | str,
) -> dict[str, Any]:
    service = client.create_tagmanager_client()
    path = utils.construct_version_path(account_id, container_id, version_id)
    response = client.execute(
        service.accounts().containers().versions().publish(path=path),
        mutating=True,
    )
    version = response.get('containerVersion', {})
    return {
        'containerVersionId': version.get('containerVersionId'),
        'compilerError': response.get('compilerError', False),
        'containerVersion': utils.slim_container_version(version),
    }
