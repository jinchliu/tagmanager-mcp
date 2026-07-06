"""Shared plumbing for calling the Google Tag Manager API.

Mirrors the analytics-mcp reference shape: ADC credentials are loaded
lazily once and cached under a lock, while a fresh discovery client is
built per call. All API executions go through execute(), which adds
throttling, retry with backoff, and actionable error messages.
"""

import contextlib
import importlib.metadata
import json
import random
import subprocess
import threading
import time
from typing import Any, Iterator
from unittest.mock import patch

import google.auth
import google.auth.exceptions
import google_auth_httplib2
import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import set_user_agent

READ_ONLY_SCOPE = 'https://www.googleapis.com/auth/tagmanager.readonly'

_HTTP_TIMEOUT_SECONDS = 30
# Worst-case backoff ~61s: rides out most of the 100s quota window
# without exceeding common MCP client tool-call timeouts.
_MAX_RETRIES = 5
_MAX_SLEEP_SECONDS = 30.0
_THROTTLE_INTERVAL_SECONDS = 4.0

# GTM quota is 25 requests per 100s sliding window, per GCP project.
# Legacy endpoints signal it via 403 + these reasons; modern ones via
# 429, so both are treated as retryable.
_RETRYABLE_REASONS = frozenset(
    {'userRateLimitExceeded', 'quotaExceeded', 'rateLimitExceeded'}
)

_LOGIN_COMMAND = (
    'gcloud auth application-default login'
    ' --scopes=https://www.googleapis.com/auth/tagmanager.readonly,'
    'https://www.googleapis.com/auth/analytics.readonly,'
    'https://www.googleapis.com/auth/cloud-platform'
)
_ADC_SETUP_HINT = (
    'Set up Application Default Credentials:\n'
    '  gcloud services enable tagmanager.googleapis.com'
    ' --project=YOUR_PROJECT\n'
    f'  {_LOGIN_COMMAND}\n'
    '  gcloud auth application-default set-quota-project YOUR_PROJECT'
)

_credentials_lock = threading.Lock()
_credentials: Any = None

_throttle_lock = threading.Lock()
_throttle_enabled = False
_last_request_at = 0.0


@contextlib.contextmanager
def prevent_stdio_inheritance() -> Iterator[None]:
    """Prevents child processes from inheriting this server's stdio.

    On Windows, google.auth.default() may spawn gcloud without
    redirecting stdin; the child then inherits the event loop's stdio
    handles used by the MCP transport and deadlocks. Forcing
    stdin=DEVNULL on children whose stdin is unset avoids that.
    """
    original_popen = subprocess.Popen

    def safe_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        if kwargs.get('stdin') is None:
            kwargs['stdin'] = subprocess.DEVNULL
        return original_popen(*args, **kwargs)

    with patch('subprocess.Popen', new=safe_popen):
        yield


def _package_version() -> str:
    try:
        return importlib.metadata.version('tagmanager-mcp')
    except importlib.metadata.PackageNotFoundError:
        return 'unknown'


def _get_credentials() -> Any:
    """Loads ADC credentials once; thread-safe."""
    global _credentials
    with _credentials_lock:
        if _credentials is None:
            try:
                with prevent_stdio_inheritance():
                    _credentials, _ = google.auth.default(
                        scopes=[READ_ONLY_SCOPE]
                    )
            except google.auth.exceptions.DefaultCredentialsError as error:
                raise RuntimeError(
                    f'No Google credentials found. {_ADC_SETUP_HINT}'
                ) from error
        return _credentials


def create_tagmanager_client() -> Any:
    """Builds a Tag Manager v2 discovery client with shared credentials."""
    http = set_user_agent(
        httplib2.Http(timeout=_HTTP_TIMEOUT_SECONDS),
        f'tagmanager-mcp/{_package_version()}',
    )
    authorized_http = google_auth_httplib2.AuthorizedHttp(
        _get_credentials(), http=http
    )
    return build(
        'tagmanager', 'v2', http=authorized_http, cache_discovery=False
    )


def _error_reasons(error: HttpError) -> set[str]:
    """Collects machine-readable reason codes from an API error body.

    The body is untrusted input (proxies can return HTML, payloads can
    be strings instead of dicts), so any parse failure yields whatever
    was collected so far rather than raising.
    """
    reasons: set[str] = set()
    try:
        payload = json.loads(error.content.decode('utf-8'))['error']
        reasons.add(payload.get('status', ''))
        for item in payload.get('errors', []) + payload.get('details', []):
            reasons.add(item.get('reason', ''))
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        UnicodeDecodeError,
    ):
        pass
    reasons.discard('')
    return reasons


def _should_retry(status: int, reasons: set[str]) -> bool:
    if status == 429 or status >= 500:
        return True
    return status == 403 and bool(reasons & _RETRYABLE_REASONS)


def _actionable_message(
    status: int, reasons: set[str], error: HttpError
) -> str:
    """Maps an API error to a message that tells the caller what to do."""
    # The discovery client surfaces scope problems in legacy format
    # (reason 'insufficientPermissions' + a message about scopes), not
    # as an ACCESS_TOKEN_SCOPE_INSUFFICIENT detail like raw REST does.
    if 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons or (
        'authentication scopes' in str(error).lower()
    ):
        return (
            'The ADC token lacks the Tag Manager scope. Re-run:\n'
            f'  {_LOGIN_COMMAND}'
        )
    if 'accessNotConfigured' in reasons or 'SERVICE_DISABLED' in reasons:
        return (
            'The Tag Manager API is not enabled on the quota project.'
            ' Run: gcloud services enable tagmanager.googleapis.com'
            ' --project=YOUR_PROJECT'
        )
    if status == 404:
        return (
            'Resource not found. Check the account/container/workspace'
            '/entity IDs; the list_* tools show the valid ones.'
        )
    if status == 403:
        return (
            'Permission denied. Verify that the authenticated Google'
            ' account has access to this GTM resource, or fix the ADC'
            f' setup.\n{_ADC_SETUP_HINT}'
        )
    return f'Tag Manager API error (HTTP {status}): {error}'


def _retry_sleep_seconds(error: HttpError, attempt: int) -> float:
    retry_after = error.resp.get('retry-after') if error.resp else None
    if retry_after:
        try:
            return min(float(retry_after), _MAX_SLEEP_SECONDS)
        except ValueError:
            pass
    return min(2.0**attempt + random.uniform(0, 1), _MAX_SLEEP_SECONDS)


def _enable_throttle() -> None:
    global _throttle_enabled
    with _throttle_lock:
        _throttle_enabled = True


def _respect_throttle() -> None:
    """Spaces out requests once a rate limit has been hit."""
    global _last_request_at
    with _throttle_lock:
        if _throttle_enabled:
            wait = _THROTTLE_INTERVAL_SECONDS - (
                time.monotonic() - _last_request_at
            )
            if wait > 0:
                time.sleep(wait)
        _last_request_at = time.monotonic()


def execute(request: Any) -> dict[str, Any]:
    """Executes a googleapiclient request with retry and throttling.

    Raises RuntimeError with an actionable message instead of leaking a
    raw HttpError to the model.
    """
    for attempt in range(_MAX_RETRIES + 1):
        _respect_throttle()
        try:
            return request.execute()
        except google.auth.exceptions.RefreshError as error:
            raise RuntimeError(
                'Could not refresh Google credentials (expired or'
                f' revoked). Re-run:\n  {_LOGIN_COMMAND}'
            ) from error
        except (OSError, httplib2.HttpLib2Error) as error:
            raise RuntimeError(
                'Network error reaching tagmanager.googleapis.com:'
                f' {error!r}. Check connectivity and proxy settings.'
            ) from error
        except HttpError as error:
            status = error.resp.status if error.resp else 0
            reasons = _error_reasons(error)
            if not _should_retry(status, reasons):
                raise RuntimeError(
                    _actionable_message(status, reasons, error)
                ) from error
            _enable_throttle()
            if attempt == _MAX_RETRIES:
                raise RuntimeError(
                    'Tag Manager API rate limit persisted through'
                    f' {_MAX_RETRIES} retries. The quota is 25 requests'
                    ' per 100 seconds per project; wait a minute, then'
                    ' retry.'
                ) from error
            time.sleep(_retry_sleep_seconds(error, attempt))
    raise AssertionError('unreachable')
