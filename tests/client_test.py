"""Offline unit tests for the error/retry logic in client.py."""

import json
import unittest
from typing import Any
from unittest import mock

import google.auth.exceptions
import httplib2
from googleapiclient.errors import HttpError

from tagmanager_mcp.tools import client


def _http_error(status: int, payload: dict[str, Any]) -> HttpError:
    resp = httplib2.Response({'status': status})
    return HttpError(resp, json.dumps({'error': payload}).encode('utf-8'))


class ShouldRetryTest(unittest.TestCase):
    def test_429_retries(self) -> None:
        self.assertTrue(client._should_retry(429, set()))

    def test_403_rate_limit_reason_retries(self) -> None:
        self.assertTrue(client._should_retry(403, {'userRateLimitExceeded'}))

    def test_403_scope_error_does_not_retry(self) -> None:
        self.assertFalse(
            client._should_retry(403, {'ACCESS_TOKEN_SCOPE_INSUFFICIENT'})
        )

    def test_404_does_not_retry(self) -> None:
        self.assertFalse(client._should_retry(404, set()))

    def test_5xx_retries(self) -> None:
        self.assertTrue(client._should_retry(500, set()))
        self.assertTrue(client._should_retry(503, set()))


class ErrorReasonsTest(unittest.TestCase):
    def test_collects_legacy_and_v2_reasons(self) -> None:
        error = _http_error(
            403,
            {
                'errors': [{'reason': 'insufficientPermissions'}],
                'details': [{'reason': 'ACCESS_TOKEN_SCOPE_INSUFFICIENT'}],
                'status': 'PERMISSION_DENIED',
            },
        )
        reasons = client._error_reasons(error)
        self.assertIn('insufficientPermissions', reasons)
        self.assertIn('ACCESS_TOKEN_SCOPE_INSUFFICIENT', reasons)
        self.assertIn('PERMISSION_DENIED', reasons)

    def test_garbage_body_yields_empty_set(self) -> None:
        error = HttpError(httplib2.Response({'status': 500}), b'not json')
        self.assertEqual(client._error_reasons(error), set())

    def test_string_error_payload_yields_empty_set(self) -> None:
        error = HttpError(
            httplib2.Response({'status': 403}),
            b'{"error": "invalid_request"}',
        )
        self.assertEqual(client._error_reasons(error), set())


class ActionableMessageTest(unittest.TestCase):
    def test_scope_error_mentions_login_command(self) -> None:
        error = _http_error(403, {'status': 'PERMISSION_DENIED'})
        message = client._actionable_message(
            403, {'ACCESS_TOKEN_SCOPE_INSUFFICIENT'}, error
        )
        self.assertIn('application-default login', message)

    def test_legacy_scope_message_mentions_login_command(self) -> None:
        # Discovery-client-shaped 403: no ACCESS_TOKEN_SCOPE_INSUFFICIENT
        # detail, only the legacy message text.
        error = _http_error(
            403,
            {
                'message': 'Request had insufficient authentication' ' scopes.',
                'errors': [{'reason': 'insufficientPermissions'}],
                'status': 'PERMISSION_DENIED',
            },
        )
        message = client._actionable_message(
            403, client._error_reasons(error), error
        )
        self.assertIn('application-default login', message)

    def test_api_disabled_mentions_enable_command(self) -> None:
        error = _http_error(403, {'status': 'PERMISSION_DENIED'})
        message = client._actionable_message(
            403, {'accessNotConfigured'}, error
        )
        self.assertIn('services enable', message)

    def test_404_mentions_ids(self) -> None:
        error = _http_error(404, {'status': 'NOT_FOUND'})
        message = client._actionable_message(404, {'NOT_FOUND'}, error)
        self.assertIn('list_', message)


class ExecuteTest(unittest.TestCase):
    def setUp(self) -> None:
        client._throttle_enabled = False

    def test_retries_rate_limit_then_succeeds(self) -> None:
        rate_limited = _http_error(429, {'status': 'RESOURCE_EXHAUSTED'})
        request = mock.Mock()
        request.execute.side_effect = [rate_limited, {'ok': True}]
        with mock.patch.object(client.time, 'sleep'):
            self.assertEqual(client.execute(request), {'ok': True})
        self.assertEqual(request.execute.call_count, 2)
        self.assertTrue(client._throttle_enabled)

    def test_non_retryable_raises_runtime_error(self) -> None:
        request = mock.Mock()
        request.execute.side_effect = _http_error(404, {'status': 'NOT_FOUND'})
        with mock.patch.object(client.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                client.execute(request)
        self.assertEqual(request.execute.call_count, 1)

    def test_exhausted_retries_raise_actionable_error(self) -> None:
        request = mock.Mock()
        request.execute.side_effect = _http_error(
            429, {'status': 'RESOURCE_EXHAUSTED'}
        )
        with mock.patch.object(client.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '25 requests'):
                client.execute(request)
        self.assertEqual(request.execute.call_count, client._MAX_RETRIES + 1)

    def test_refresh_error_maps_to_login_hint(self) -> None:
        request = mock.Mock()
        request.execute.side_effect = google.auth.exceptions.RefreshError(
            'invalid_grant'
        )
        with mock.patch.object(client.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'application-default'):
                client.execute(request)

    def test_network_error_maps_to_actionable_message(self) -> None:
        request = mock.Mock()
        request.execute.side_effect = TimeoutError('timed out')
        with mock.patch.object(client.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Network error'):
                client.execute(request)

    def test_retry_after_header_wins_over_backoff(self) -> None:
        resp = httplib2.Response({'status': 429, 'retry-after': '7'})
        error = HttpError(
            resp,
            json.dumps({'error': {'status': 'RESOURCE_EXHAUSTED'}}).encode(
                'utf-8'
            ),
        )
        self.assertEqual(client._retry_sleep_seconds(error, 0), 7.0)


if __name__ == '__main__':
    unittest.main()
