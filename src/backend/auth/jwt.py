"""Minimal HS256 JSON Web Token support for TradeLens access tokens."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def issue_access_token(user: dict[str, object], secret: str, expires_in_seconds: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": str(user["email"]),
        "is_admin": bool(user.get("is_admin", False)),
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_encode(header)}.{_encode(payload)}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_encode_bytes(signature)}"


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(
            secret.encode("utf-8"), f"{header}.{payload}".encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _decode_bytes(signature)):
            raise ValueError("Invalid token signature")
        claims = json.loads(_decode_bytes(payload))
        if not isinstance(claims, dict) or int(claims["exp"]) <= int(time.time()):
            raise ValueError("Token has expired")
        return claims
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Invalid or expired access token") from error


def _encode(value: dict[str, object]) -> str:
    return _encode_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
