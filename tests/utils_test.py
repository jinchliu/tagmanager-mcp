"""Offline unit tests for tagmanager_mcp.tools.utils."""

import unittest
from typing import Any

from tagmanager_mcp.tools import utils


class _FakePage:
    """Stands in for a googleapiclient request; execute() is offline."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def execute(self) -> dict[str, Any]:
        return self._response


class ConstructPathTest(unittest.TestCase):
    def test_account_path_from_int(self) -> None:
        self.assertEqual(utils.construct_account_path(123), 'accounts/123')

    def test_account_path_from_digit_string(self) -> None:
        self.assertEqual(utils.construct_account_path('123'), 'accounts/123')

    def test_account_path_strips_whitespace(self) -> None:
        self.assertEqual(utils.construct_account_path(' 123 '), 'accounts/123')

    def test_account_path_from_full_path(self) -> None:
        self.assertEqual(
            utils.construct_account_path('accounts/123'), 'accounts/123'
        )

    def test_container_path(self) -> None:
        self.assertEqual(
            utils.construct_container_path(1, '2'),
            'accounts/1/containers/2',
        )

    def test_workspace_path_accepts_full_path_per_argument(self) -> None:
        full = 'accounts/1/containers/2/workspaces/3'
        self.assertEqual(utils.construct_workspace_path(full, full, full), full)

    def test_entity_path(self) -> None:
        self.assertEqual(
            utils.construct_entity_path(1, 2, 3, 'tags', 7),
            'accounts/1/containers/2/workspaces/3/tags/7',
        )

    def test_version_path(self) -> None:
        self.assertEqual(
            utils.construct_version_path(1, 2, 9),
            'accounts/1/containers/2/versions/9',
        )

    def test_version_path_from_full_path(self) -> None:
        full = 'accounts/1/containers/2/versions/9'
        self.assertEqual(utils.construct_version_path(1, 2, full), full)

    def test_rejects_non_numeric(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path('abc')

    def test_rejects_empty_string(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path('')

    def test_rejects_bool(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path(True)

    def test_rejects_partial_path(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path('accounts/')

    def test_rejects_path_missing_wanted_segment(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path('containers/456')


class SlimTest(unittest.TestCase):
    def test_slim_tag_drops_verbose_fields(self) -> None:
        tag = {
            'tagId': '1',
            'name': 'GA4 event',
            'type': 'gaawe',
            'firingTriggerId': ['5'],
            'fingerprint': 'fp',
            'parameter': [{'type': 'template', 'key': 'x', 'value': 'y'}],
            'monitoringMetadata': {'type': 'map'},
        }
        self.assertEqual(
            utils.slim_tag(tag),
            {
                'tagId': '1',
                'name': 'GA4 event',
                'type': 'gaawe',
                'firingTriggerId': ['5'],
                'fingerprint': 'fp',
            },
        )

    def test_slim_tolerates_missing_fields(self) -> None:
        self.assertEqual(utils.slim_trigger({}), {})
        self.assertEqual(utils.slim_variable({'name': 'v'}), {'name': 'v'})

    def test_slim_version_header_keeps_skeleton(self) -> None:
        header = {
            'containerVersionId': '9',
            'name': 'v9',
            'numTags': 4,
            'numTriggers': 2,
            'numVariables': 1,
            'path': 'accounts/1/containers/2/versions/9',
            'accountId': '1',
        }
        self.assertEqual(
            utils.slim_version_header(header),
            {
                'containerVersionId': '9',
                'name': 'v9',
                'numTags': 4,
                'numTriggers': 2,
                'numVariables': 1,
            },
        )

    def test_slim_container_version_slims_embedded_entities(self) -> None:
        version = {
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
            'trigger': [{'triggerId': '5', 'name': 'tr', 'type': 'pageview'}],
            'variable': [{'variableId': '3', 'name': 'v', 'type': 'c'}],
        }
        self.assertEqual(
            utils.slim_container_version(version),
            {
                'containerVersionId': '9',
                'name': 'v9',
                'fingerprint': 'fp',
                'tag': [{'tagId': '1', 'name': 't', 'type': 'html'}],
                'trigger': [
                    {'triggerId': '5', 'name': 'tr', 'type': 'pageview'}
                ],
                'variable': [{'variableId': '3', 'name': 'v', 'type': 'c'}],
            },
        )

    def test_slim_container_version_tolerates_no_entities(self) -> None:
        self.assertEqual(
            utils.slim_container_version({'containerVersionId': '9'}),
            {'containerVersionId': '9'},
        )


class ExtractIdEdgeCaseTest(unittest.TestCase):
    def test_rejects_fullwidth_digits(self) -> None:
        # str.isdigit() alone would accept these.
        with self.assertRaises(ValueError):
            utils.construct_account_path('１２３')

    def test_rejects_fullwidth_digits_in_path(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path('accounts/１２３')

    def test_rejects_negative_int(self) -> None:
        with self.assertRaises(ValueError):
            utils.construct_account_path(-5)


class MergePatchTest(unittest.TestCase):
    def test_replaces_and_adds_fields(self) -> None:
        base = {'name': 'old', 'paused': False}
        patch = {'name': 'new', 'notes': 'added'}
        self.assertEqual(
            utils.merge_patch(base, patch),
            {'name': 'new', 'paused': False, 'notes': 'added'},
        )

    def test_null_removes_field(self) -> None:
        self.assertEqual(
            utils.merge_patch({'name': 'x', 'notes': 'y'}, {'notes': None}),
            {'name': 'x'},
        )

    def test_removing_missing_key_is_noop(self) -> None:
        self.assertEqual(
            utils.merge_patch({'name': 'x'}, {'notes': None}), {'name': 'x'}
        )

    def test_lists_replaced_whole(self) -> None:
        base = {'firingTriggerId': ['1', '2']}
        patch = {'firingTriggerId': ['3']}
        self.assertEqual(
            utils.merge_patch(base, patch), {'firingTriggerId': ['3']}
        )

    def test_nested_dicts_not_deep_merged(self) -> None:
        base = {'monitoringMetadata': {'type': 'map', 'map': [{'key': 'a'}]}}
        patch = {'monitoringMetadata': {'type': 'map'}}
        self.assertEqual(
            utils.merge_patch(base, patch),
            {'monitoringMetadata': {'type': 'map'}},
        )

    def test_base_not_mutated(self) -> None:
        base = {'name': 'old'}
        utils.merge_patch(base, {'name': 'new', 'notes': 'x'})
        self.assertEqual(base, {'name': 'old'})


class PaginateTest(unittest.TestCase):
    def test_aggregates_pages(self) -> None:
        pages = {
            None: {'account': [{'accountId': '1'}], 'nextPageToken': 'p2'},
            'p2': {'account': [{'accountId': '2'}]},
        }
        result = utils.paginate(
            lambda token: _FakePage(pages[token]), 'account'
        )
        self.assertEqual([item['accountId'] for item in result], ['1', '2'])

    def test_empty_response_returns_empty_list(self) -> None:
        result = utils.paginate(lambda token: _FakePage({}), 'account')
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
