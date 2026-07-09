"""Offline tests for the v0.3 version tools (list/get/live/create/publish).

The discovery client and client.execute are mocked; no network access.
"""

import asyncio
import unittest
from typing import Any
from unittest import mock

from tagmanager_mcp.tools import client, versions

_CONTAINER = 'accounts/1/containers/2'
_WORKSPACE = f'{_CONTAINER}/workspaces/3'
_VERSION = f'{_CONTAINER}/versions/9'


def _service_and_containers() -> tuple[mock.Mock, mock.Mock]:
    """Builds a discovery-client mock exposing the containers collection."""
    service = mock.Mock()
    containers = service.accounts.return_value.containers.return_value
    return service, containers


class ListVersionsTest(unittest.TestCase):
    def test_paginates_and_slims_headers(self) -> None:
        service, containers = _service_and_containers()
        list_api = containers.version_headers.return_value.list

        def fake_execute(request: Any, mutating: bool = False) -> Any:
            return {
                'containerVersionHeader': [
                    {
                        'containerVersionId': '9',
                        'name': 'v9',
                        'numTags': 4,
                        'path': 'accounts/1/containers/2/versions/9',
                    }
                ]
            }

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', side_effect=fake_execute):
                result = asyncio.run(versions.list_versions(1, 2))

        list_api.assert_called_once_with(parent=_CONTAINER, pageToken=None)
        self.assertEqual(
            result,
            {
                'versions': [
                    {'containerVersionId': '9', 'name': 'v9', 'numTags': 4}
                ]
            },
        )


class GetVersionTest(unittest.TestCase):
    def test_get_reads_path_and_slims_embedded_entities(self) -> None:
        service, containers = _service_and_containers()
        get_request = mock.Mock()
        containers.versions.return_value.get.return_value = get_request
        full = {
            'containerVersionId': '9',
            'name': 'v9',
            'fingerprint': 'fp',
            'tag': [
                {
                    'tagId': '1',
                    'name': 't',
                    'type': 'html',
                    'parameter': [{'key': 'html', 'value': '<x>'}],
                }
            ],
        }

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', return_value=full):
                result = asyncio.run(versions.get_version(1, 2, 9))

        containers.versions.return_value.get.assert_called_once_with(
            path=_VERSION
        )
        self.assertEqual(
            result,
            {
                'containerVersionId': '9',
                'name': 'v9',
                'fingerprint': 'fp',
                'tag': [{'tagId': '1', 'name': 't', 'type': 'html'}],
            },
        )


class GetLiveVersionTest(unittest.TestCase):
    def test_live_reads_container_parent(self) -> None:
        service, containers = _service_and_containers()
        live_api = containers.versions.return_value.live

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(
                client, 'execute', return_value={'containerVersionId': '9'}
            ):
                result = asyncio.run(versions.get_live_version(1, 2))

        live_api.assert_called_once_with(parent=_CONTAINER)
        self.assertEqual(result, {'containerVersionId': '9'})


class CreateVersionTest(unittest.TestCase):
    def test_create_passes_workspace_path_body_and_surfaces_new_workspace(
        self,
    ) -> None:
        service, containers = _service_and_containers()
        create_request = mock.Mock()
        containers.workspaces.return_value.create_version.return_value = (
            create_request
        )
        executed: list[tuple[Any, bool]] = []

        def fake_execute(request: Any, mutating: bool = False) -> Any:
            executed.append((request, mutating))
            return {
                'containerVersion': {'containerVersionId': '9', 'name': 'v9'},
                'newWorkspacePath': f'{_CONTAINER}/workspaces/4',
                'compilerError': False,
                'syncStatus': {'mergeConflict': False, 'syncError': False},
            }

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', side_effect=fake_execute):
                result = asyncio.run(
                    versions.create_version(1, 2, 3, name='v9', notes='n')
                )

        containers.workspaces.return_value.create_version.assert_called_once_with(
            path=_WORKSPACE, body={'name': 'v9', 'notes': 'n'}
        )
        self.assertEqual(executed, [(create_request, True)])
        self.assertEqual(
            result['newWorkspacePath'], f'{_CONTAINER}/workspaces/4'
        )
        self.assertEqual(result['containerVersionId'], '9')
        self.assertFalse(result['compilerError'])
        self.assertEqual(
            result['containerVersion'],
            {'containerVersionId': '9', 'name': 'v9'},
        )

    def test_create_omits_unset_name_and_notes(self) -> None:
        service, containers = _service_and_containers()

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', return_value={}):
                asyncio.run(versions.create_version(1, 2, 3))

        containers.workspaces.return_value.create_version.assert_called_once_with(
            path=_WORKSPACE, body={}
        )

    def test_create_tolerates_response_without_container_version(self) -> None:
        # An empty workspace may yield a response with no containerVersion.
        service, containers = _service_and_containers()

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', return_value={}):
                result = asyncio.run(versions.create_version(1, 2, 3))

        self.assertIsNone(result['containerVersionId'])
        self.assertIsNone(result['newWorkspacePath'])
        self.assertEqual(result['containerVersion'], {})


class PublishVersionTest(unittest.TestCase):
    def test_publish_without_confirm_refuses_before_any_api_call(self) -> None:
        with mock.patch.object(client, 'create_tagmanager_client') as factory:
            with self.assertRaisesRegex(ValueError, 'confirm=True'):
                asyncio.run(versions.publish_version(1, 2, 9))
        factory.assert_not_called()

    def test_confirmed_publish_calls_api_with_version_path(self) -> None:
        service, containers = _service_and_containers()
        publish_request = mock.Mock()
        containers.versions.return_value.publish.return_value = publish_request
        executed: list[tuple[Any, bool]] = []

        def fake_execute(request: Any, mutating: bool = False) -> Any:
            executed.append((request, mutating))
            return {
                'containerVersion': {'containerVersionId': '9'},
                'compilerError': False,
            }

        with mock.patch.object(
            client, 'create_tagmanager_client', return_value=service
        ):
            with mock.patch.object(client, 'execute', side_effect=fake_execute):
                result = asyncio.run(
                    versions.publish_version(1, 2, 9, confirm=True)
                )

        containers.versions.return_value.publish.assert_called_once_with(
            path=_VERSION
        )
        self.assertEqual(executed, [(publish_request, True)])
        self.assertEqual(result['containerVersionId'], '9')
        self.assertFalse(result['compilerError'])


if __name__ == '__main__':
    unittest.main()
