from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any

from auth.service import AuthService


class ApiHandler(BaseHTTPRequestHandler):
    service: AuthService

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _access_token(self) -> str:
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            raise ValueError("Authorization bearer token is required")
        return authorization.removeprefix("Bearer ").strip()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0].rstrip("/") or "/"
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "service": "tradelens-backend"},
            )
            return
        if path == "/api/auth/me":
            try:
                user = self.service.current_user(self._access_token())
            except ValueError as exc:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, {"user": user})
            return
        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                {"message": "TradeLens backend", "health": "/api/health"},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0].rstrip("/") or "/"
        if path not in {"/api/register", "/api/login"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            payload = self._read_json()
            if path == "/api/login":
                authentication = self.service.login(
                    payload.get("email", ""), payload.get("password", "")
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "accessToken": authentication.access_token,
                        "user": {
                            "id": authentication.user_id,
                            "email": authentication.email,
                            "isAdmin": authentication.is_admin,
                        },
                    },
                )
                return
            registration = self.service.register(
                payload.get("email", ""),
                payload.get("password", ""),
                payload.get("confirmPassword", ""),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(
            HTTPStatus.CREATED,
            {
                "status": "created",
                "user": {"id": registration.user_id, "email": registration.email},
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")
