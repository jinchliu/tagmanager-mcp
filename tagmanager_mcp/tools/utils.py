"""Resource-path construction and response-slimming helpers."""

import re
from typing import Any, Callable

from tagmanager_mcp.tools import client

_TAG_SKELETON_FIELDS = (
    'tagId',
    'name',
    'type',
    'firingTriggerId',
    'blockingTriggerId',
    'paused',
    'fingerprint',
)
_TRIGGER_SKELETON_FIELDS = ('triggerId', 'name', 'type', 'fingerprint')
_VARIABLE_SKELETON_FIELDS = ('variableId', 'name', 'type', 'fingerprint')


def _extract_id(value: int | str, segment: str) -> str:
    """Extracts the numeric ID for one path segment.

    Accepts an int, a numeric string, or any resource path containing
    '{segment}/{id}' (e.g. 'accounts/123/containers/456').
    """
    if isinstance(value, int) and not isinstance(value, bool):
        if value >= 0:
            return str(value)
    if isinstance(value, str):
        # ASCII-only: str.isdigit() and \d also match Unicode digits
        # (e.g. fullwidth '１２３'), which would corrupt the API path.
        text = value.strip()
        if text.isascii() and text.isdigit():
            return text
        match = re.search(rf'(?:^|/){segment}/([0-9]+)(?:/|$)', text)
        if match:
            return match.group(1)
    raise ValueError(
        f'Invalid {segment[:-1]}_id: {value!r}. Pass a numeric ID'
        " (e.g. 123456) or a full resource path (e.g."
        " 'accounts/123/containers/456/workspaces/7')."
    )


def construct_account_path(account_id: int | str) -> str:
    """Returns 'accounts/{id}'."""
    return f'accounts/{_extract_id(account_id, "accounts")}'


def construct_container_path(
    account_id: int | str, container_id: int | str
) -> str:
    """Returns 'accounts/{a}/containers/{c}'."""
    container = _extract_id(container_id, 'containers')
    return f'{construct_account_path(account_id)}/containers/{container}'


def construct_workspace_path(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
) -> str:
    """Returns 'accounts/{a}/containers/{c}/workspaces/{w}'."""
    workspace = _extract_id(workspace_id, 'workspaces')
    container_path = construct_container_path(account_id, container_id)
    return f'{container_path}/workspaces/{workspace}'


def construct_entity_path(
    account_id: int | str,
    container_id: int | str,
    workspace_id: int | str,
    kind: str,
    entity_id: int | str,
) -> str:
    """Returns a workspace-scoped entity path, e.g. '.../tags/{id}'."""
    workspace_path = construct_workspace_path(
        account_id, container_id, workspace_id
    )
    return f'{workspace_path}/{kind}/{_extract_id(entity_id, kind)}'


def _slim(entity: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: entity[key] for key in fields if key in entity}


def slim_tag(tag: dict[str, Any]) -> dict[str, Any]:
    """Keeps skeleton fields only; get_tag returns the full config."""
    return _slim(tag, _TAG_SKELETON_FIELDS)


def slim_trigger(trigger: dict[str, Any]) -> dict[str, Any]:
    """Keeps skeleton fields only; get_trigger returns the full config."""
    return _slim(trigger, _TRIGGER_SKELETON_FIELDS)


def slim_variable(variable: dict[str, Any]) -> dict[str, Any]:
    """Keeps skeleton fields only; get_variable returns the full config."""
    return _slim(variable, _VARIABLE_SKELETON_FIELDS)


def paginate(
    make_request: Callable[[str | None], Any], items_key: str
) -> list[dict[str, Any]]:
    """Fetches all pages of a list method.

    The API omits the items array entirely when a page is empty, hence
    the .get() with a default.
    """
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        response = client.execute(make_request(page_token))
        items.extend(response.get(items_key, []))
        page_token = response.get('nextPageToken')
        if not page_token:
            return items
