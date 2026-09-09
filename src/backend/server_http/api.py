from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlsplit

from auth.service import AuthService
from pattern_engine.query_service import PatternQueryService, browser_payload
from pattern_engine.research import BacktestService


class ApiHandler(BaseHTTPRequestHandler):
    service: AuthService
    pattern_service: PatternQueryService
    research_service: BacktestService
    admin_pipeline_service: Any

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(browser_payload(payload)).encode("utf-8")
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
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query, keep_blank_values=True)
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "service": "tradelens-backend"},
            )
            return
        if path == "/api/auth/me":
            try:
                user, access_token = self.service.renew_access_token(self._access_token())
            except ValueError as exc:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, {
                "accessToken": access_token,
                "user": {
                    "id": user.get("id"), "email": user.get("email"),
                    "isAdmin": bool(user.get("is_admin", False)),
                },
            })
            return
        if path.startswith("/api/admin/"):
            user = self._authorize_admin()
            if user is None:
                return
            try:
                if path == "/api/admin/equities":
                    payload = self.admin_pipeline_service.list_equities(query)
                elif path == "/api/admin/pipeline/runs":
                    payload = self.admin_pipeline_service.list_runs(query)
                else:
                    parts = path.strip("/").split("/")
                    if len(parts) == 5 and parts[:4] == ["api", "admin", "pipeline", "runs"]:
                        payload = self.admin_pipeline_service.get_run(parts[4], query)
                    else:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                        return
            except LookupError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            except (TypeError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if self._is_pattern_path(path):
            try:
                self.service.current_user(self._access_token())
            except ValueError as exc:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return
            try:
                payload = self._pattern_get(path, query)
            except LookupError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            except (TypeError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if payload is not None:
                self._send_json(HTTPStatus.OK, payload)
                return
        if path == "/":
            self._send_json(
                HTTPStatus.OK,
                {"message": "TradeLens backend", "health": "/api/health"},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    @staticmethod
    def _is_pattern_path(path):
        if path in {"/api/overview", "/api/setups", "/api/securities/search"}:
            return True
        parts = path.strip("/").split("/")
        return (
            len(parts) == 3 and parts[:2] == ["api", "patterns"]
            or len(parts) == 4 and parts[:2] == ["api", "patterns"] and parts[3] in {"events", "chart"}
            or len(parts) == 4 and parts[:2] == ["api", "securities"] and parts[3] == "fingerprint"
            or len(parts) == 4 and parts[:2] == ["api", "securities"] and parts[3] == "chart"
            or len(parts) == 4 and parts[:3] == ["api", "research", "runs"]
            or len(parts) == 5 and parts[:3] == ["api", "research", "runs"] and parts[4] == "results"
        )

    def _pattern_get(self, path, query):
        if path == "/api/overview":
            return self.pattern_service.overview(query)
        if path == "/api/setups":
            return self.pattern_service.setups(query)
        if path == "/api/securities/search":
            return self.pattern_service.search_securities(query)
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "patterns"]:
            return self.pattern_service.pattern(parts[2])
        if len(parts) == 4 and parts[:2] == ["api", "patterns"] and parts[3] == "events":
            return self.pattern_service.events(parts[2], query)
        if len(parts) == 4 and parts[:2] == ["api", "patterns"] and parts[3] == "chart":
            return self.pattern_service.chart(parts[2], query)
        if len(parts) == 4 and parts[:2] == ["api", "securities"] and parts[3] == "fingerprint":
            return self.pattern_service.fingerprint(parts[2], query)
        if len(parts) == 4 and parts[:2] == ["api", "securities"] and parts[3] == "chart":
            return self.pattern_service.security_chart(parts[2], query)
        if len(parts) == 4 and parts[:3] == ["api", "research", "runs"]:
            return self.research_service.get_run(parts[3])
        if len(parts) == 5 and parts[:3] == ["api", "research", "runs"] and parts[4] == "results":
            return self.research_service.results(parts[3], query)
        return None

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0].rstrip("/") or "/"
        parts = path.strip("/").split("/")
        if len(parts) == 6 and parts[:4] == ["api", "admin", "pipeline", "runs"]:
            user = self._authorize_admin()
            if user is None:
                return
            action = parts[5]
            if action not in {"pause", "resume", "terminate"}:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            try:
                result = getattr(self.admin_pipeline_service, action)(parts[4])
            except LookupError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            except ValueError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.ACCEPTED if action == "resume" else HTTPStatus.OK,
                result,
            )
            return
        if path == "/api/admin/pipeline/runs":
            user = self._authorize_admin()
            if user is None:
                return
            try:
                result = self.admin_pipeline_service.start(
                    self._read_json(), str(user.get("id") or "")
                )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.ACCEPTED, result)
            return
        if path == "/api/research/runs":
            try:
                user = self.service.current_user(self._access_token())
            except ValueError as exc:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
                return
            try:
                result = self.research_service.start(self._read_json(), str(user.get("id") or "") or None)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError as exc:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.CREATED, result)
            return
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

    def _authorize_admin(self):
        try:
            user = self.service.current_user(self._access_token())
        except ValueError as exc:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
            return None
        if not bool(user.get("is_admin", False)):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Administrator access is required"})
            return None
        return user

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")
