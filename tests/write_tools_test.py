"""Offline tests for the v0.2 write tools (create/update/delete).

The discovery client and client.execute are mocked; the three entity
modules are isomorphic, so every test loops over all of them.
"""

import asyncio
import unittest
from typing import Any
from unittest import mock

from tagmanager_mcp.tools import client, tags, triggers, variables

_WORKSPACE = 'accounts/1/containers/2/workspaces/3'

_CASES = [
    ('tags', tags.create_tag, tags.update_tag, tags.delete_tag),
    (
        'triggers',
        triggers.create_trigger,
        triggers.update_trigger,
        triggers.delete_trigger,
    ),
    (
        'variables',
        variables.create_variable,
        variables.update_variable,
        variables.delete_variable,
    ),
]


def _service_and_api(kind: str) -> tuple[mock.Mock, mock.Mock]:
    """Builds a discovery-client mock exposing one entity collection."""
    service = mock.Mock()
    workspaces = (
        service.accounts.return_value.containers.return_value.workspaces.return_value
    )
    return service, getattr(workspaces, kind).return_value


class CreateTest(unittest.TestCase):
    def test_create_passes_body_and_mutating_flag(self) -> None:
        for kind, create_tool, _, _ in _CASES:
            with self.subTest(kind=kind):
                service, api = _service_and_api(kind)
                create_request = mock.Mock()
                api.create.return_value = create_request
                executed: list[tuple[Any, bool]] = []

                def fake_execute(
                    request: Any, mutating: bool = False
                ) -> dict[str, Any]:
                    executed.append((request, mutating))
                    return {'created': True}

                with mock.patch.object(
                    client, 'create_tagmanager_client', return_value=service
                ):
                    with mock.patch.object(
                        client, 'execute', side_effect=fake_execute
                    ):
                        result = asyncio.run(
                            create_tool(1, 2, 3, {'name': 'X', 'type': 't'})
                        )
                self.assertEqual(result, {'created': True})
                api.create.assert_called_once_with(
                    parent=_WORKSPACE, body={'name': 'X', 'type': 't'}
                )
                self.assertEqual(executed, [(create_request, True)])


class UpdateTest(unittest.TestCase):
    def test_update_rereads_merges_and_sends_fingerprint(self) -> None:
        for kind, _, update_tool, _ in _CASES:
            with self.subTest(kind=kind):
                service, api = _service_and_api(kind)
                get_request, update_request = mock.Mock(), mock.Mock()
                api.get.return_value = get_request
                api.update.return_value = update_request
                current = {
                    'name': 'old',
                    'notes': 'stale',
                    'fingerprint': 'fp1',
                }

                def fake_execute(
                    request: Any, mutating: bool = False
                ) -> dict[str, Any]:
                    if request is get_request:
                        self.assertFalse(mutating)
                        return current
                    self.assertIs(request, update_request)
                    self.assertTrue(mutating)
                    return {'updated': True}

                with mock.patch.object(
                    client, 'create_tagmanager_client', return_value=service
                ):
                    with mock.patch.object(
                        client, 'execute', side_effect=fake_execute
                    ):
                        result = asyncio.run(
                            update_tool(
                                1, 2, 3, 7, {'name': 'new', 'notes': None}
                            )
                        )
                self.assertEqual(result, {'updated': True})
                api.get.assert_called_once_with(path=f'{_WORKSPACE}/{kind}/7')
                api.update.assert_called_once_with(
                    path=f'{_WORKSPACE}/{kind}/7',
                    body={'name': 'new', 'fingerprint': 'fp1'},
                    fingerprint='fp1',
                )

    def test_update_without_fingerprint_omits_query_param(self) -> None:
        for kind, _, update_tool, _ in _CASES:
            with self.subTest(kind=kind):
                service, api = _service_and_api(kind)
                api.get.return_value = mock.Mock()
                api.update.return_value = mock.Mock()
                responses = [{'name': 'old'}, {'updated': True}]

                def fake_execute(
                    request: Any, mutating: bool = False
                ) -> dict[str, Any]:
                    return responses.pop(0)

                with mock.patch.object(
                    client, 'create_tagmanager_client', return_value=service
                ):
                    with mock.patch.object(
                        client, 'execute', side_effect=fake_execute
                    ):
                        asyncio.run(update_tool(1, 2, 3, 7, {'name': 'new'}))
                api.update.assert_called_once_with(
                    path=f'{_WORKSPACE}/{kind}/7', body={'name': 'new'}
                )


class DeleteTest(unittest.TestCase):
    def test_delete_without_confirm_refuses_before_any_api_call(self) -> None:
        for kind, _, _, delete_tool in _CASES:
            with self.subTest(kind=kind):
                with mock.patch.object(
                    client, 'create_tagmanager_client'
                ) as factory:
                    with self.assertRaisesRegex(ValueError, 'confirm=True'):
                        asyncio.run(delete_tool(1, 2, 3, 7))
                factory.assert_not_called()

    def test_confirmed_delete_calls_api_and_reports_path(self) -> None:
        for kind, _, _, delete_tool in _CASES:
            with self.subTest(kind=kind):
                service, api = _service_and_api(kind)
                delete_request = mock.Mock()
                api.delete.return_value = delete_request
                executed: list[tuple[Any, bool]] = []

                def fake_execute(request: Any, mutating: bool = False) -> Any:
                    executed.append((request, mutating))
                    return ''

                with mock.patch.object(
                    client, 'create_tagmanager_client', return_value=service
                ):
                    with mock.patch.object(
                        client, 'execute', side_effect=fake_execute
                    ):
                        result = asyncio.run(
                            delete_tool(1, 2, 3, 7, confirm=True)
                        )
                self.assertEqual(result, {'deleted': f'{_WORKSPACE}/{kind}/7'})
                api.delete.assert_called_once_with(
                    path=f'{_WORKSPACE}/{kind}/7'
                )
                self.assertEqual(executed, [(delete_request, True)])


if __name__ == '__main__':
    unittest.main()
