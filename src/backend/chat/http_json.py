"""Bounded JSON transport with safe errors and no credential-bearing redirects."""
import json
import errno
import socket
import ssl
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from chat.errors import ChatError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def _timeout_message(upstream):
    action = "Retry, or increase the Gemini timeout in Settings." if upstream == "Gemini" else "Check the service and retry."
    return f"{upstream} did not respond within its time limit. {action}"


def post_json(url, body: bytes, headers, *, timeout: float, upstream: str):
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ChatError("UPSTREAM_INVALID_RESPONSE", f"{upstream} returned too much data.")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result
    except HTTPError as error:
        if error.code == 400:
            raise ChatError("UPSTREAM_REQUEST_REJECTED", f"{upstream} rejected the request configuration. Check the configured model and supported generation settings.") from None
        if error.code in {408, 504}:
            raise ChatError("UPSTREAM_TIMEOUT", _timeout_message(upstream), 504) from None
        if error.code in {401, 403}:
            action = "Check the API key and project permissions in Settings." if upstream == "Gemini" else "Check the service's access configuration."
            raise ChatError("UPSTREAM_ACCESS_DENIED", f"{upstream} rejected access. {action}") from None
        if error.code == 404:
            raise ChatError("UPSTREAM_NOT_FOUND", f"{upstream} could not find the configured endpoint or model. Check Settings.") from None
        code = "UPSTREAM_RATE_LIMITED" if error.code == 429 else "UPSTREAM_UNAVAILABLE"
        raise ChatError(code, f"{upstream} is temporarily unavailable. Try again later.") from None
    except (OSError, URLError, HTTPException) as error:
        reason = error.reason if isinstance(error, URLError) else error
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise ChatError("UPSTREAM_TIMEOUT", _timeout_message(upstream), 504) from None
        if isinstance(reason, socket.gaierror):
            raise ChatError("UPSTREAM_DNS_FAILED", f"The server could not resolve the hostname for {upstream}. Check the server's DNS connection.") from None
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise ChatError("UPSTREAM_TLS_FAILED", f"The server could not verify {upstream}'s TLS certificate. Check the server's trusted certificates or proxy configuration.") from None
        if isinstance(reason, PermissionError) or getattr(reason, "errno", None) in {errno.EACCES, errno.EPERM} or getattr(reason, "winerror", None) == 10013:
            raise ChatError("UPSTREAM_NETWORK_BLOCKED", f"The server process is blocked from connecting to {upstream}. Check its network permissions, firewall or proxy configuration.") from None
        raise ChatError("UPSTREAM_CONNECTION_FAILED", f"The server could not establish or maintain a connection to {upstream}. Check connectivity and retry.") from None
    except (ValueError, UnicodeError):
        raise ChatError("UPSTREAM_INVALID_RESPONSE", f"{upstream} returned an invalid response.") from None
