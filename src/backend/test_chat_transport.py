import errno
import socket
import ssl
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from chat.errors import ChatError
from chat.http_json import post_json


class ChatTransportTests(unittest.TestCase):
    def test_connection_failures_are_not_all_reported_as_timeouts(self):
        cases = (
            (URLError(PermissionError(errno.EACCES, 'private-detail')), 'UPSTREAM_NETWORK_BLOCKED', 503),
            (URLError(TimeoutError('private-detail')), 'UPSTREAM_TIMEOUT', 504),
            (TimeoutError('private-detail'), 'UPSTREAM_TIMEOUT', 504),
            (URLError(socket.gaierror(-2, 'private-detail')), 'UPSTREAM_DNS_FAILED', 503),
            (URLError(ssl.SSLCertVerificationError(1, 'private-detail')), 'UPSTREAM_TLS_FAILED', 503),
            (ConnectionResetError('private-detail'), 'UPSTREAM_CONNECTION_FAILED', 503),
        )
        for failure, code, status in cases:
            with self.subTest(code=code), patch('chat.http_json.build_opener') as opener:
                opener.return_value.open.side_effect = failure
                with self.assertRaises(ChatError) as result:
                    post_json('https://example.test', b'{}', {'x-goog-api-key': 'secret'}, timeout=45, upstream='Gemini')
                self.assertEqual(code, result.exception.code)
                self.assertEqual(status, result.exception.status)
                self.assertNotIn('private-detail', str(result.exception))
                self.assertNotIn('secret', str(result.exception))

    def test_provider_http_errors_have_actionable_safe_codes(self):
        for status, code in ((400, 'UPSTREAM_REQUEST_REJECTED'), (401, 'UPSTREAM_ACCESS_DENIED'), (403, 'UPSTREAM_ACCESS_DENIED'), (404, 'UPSTREAM_NOT_FOUND'), (429, 'UPSTREAM_RATE_LIMITED'), (504, 'UPSTREAM_TIMEOUT'), (503, 'UPSTREAM_UNAVAILABLE')):
            with self.subTest(status=status), patch('chat.http_json.build_opener') as opener:
                opener.return_value.open.side_effect = HTTPError('https://example.test', status, 'private-detail', {}, None)
                with self.assertRaises(ChatError) as result:
                    post_json('https://example.test', b'{}', {}, timeout=45, upstream='Gemini')
                self.assertEqual(code, result.exception.code)
                self.assertNotIn('private-detail', str(result.exception))
