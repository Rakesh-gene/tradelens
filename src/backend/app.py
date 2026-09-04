"""Small dependency-injected HTTP API for the TradeLens application."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional at test time
    psycopg = None

HOST = "127.0.0.1"
PORT = 9004
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(slots=True)
class RegistrationResult:
    user_id: str
    email: str


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> dict[str, Any] | None:
        ...

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        ...


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        return self._users.get(email.lower())

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        user = {
            "id": str(uuid4()),
            "email": email.lower(),
            "password_hash": password_hash,
        }
        self._users[user["email"]] = user
        return user


class PostgresUserRepository:
    def __init__(self, dsn: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        self._ensure_schema()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        email TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, email, password_hash FROM users WHERE email = %s",
                    (email.lower(),),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return {"id": str(row[0]), "email": row[1], "password_hash": row[2]}

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        user_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
                    (user_id, email.lower(), password_hash),
                )
            connection.commit()
        return {"id": user_id, "email": email.lower(), "password_hash": password_hash}


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def register(self, email: str, password: str, confirm_password: str) -> RegistrationResult:
        normalized_email = email.strip().lower()
        if not EMAIL_PATTERN.match(normalized_email):
            raise ValueError("A valid email address is required")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if password != confirm_password:
            raise ValueError("Passwords do not match")
        if self._user_repository.get_by_email(normalized_email):
            raise ValueError("An account with that email already exists")
        password_hash = self._hash_password(password)
        user = self._user_repository.create_user(normalized_email, password_hash)
        return RegistrationResult(user_id=user["id"], email=user["email"])

    @staticmethod
    def _hash_password(password: str) -> str:
        import hashlib

        return hashlib.sha256(password.encode("utf-8")).hexdigest()


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

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", maxsplit=1)[0].rstrip("/") or "/"
        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {"status": "ok", "service": "tradelens-backend"},
            )
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
        if path != "/api/register":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            payload = self._read_json()
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


def build_repository() -> UserRepository:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return PostgresUserRepository(dsn)
    return InMemoryUserRepository()


def create_server(host: str = HOST, port: int = PORT, repository: UserRepository | None = None) -> ThreadingHTTPServer:
    repository = repository or build_repository()
    service = AuthService(repository)

    class ConfiguredApiHandler(ApiHandler):
        pass

    ConfiguredApiHandler.service = service
    return ThreadingHTTPServer((host, port), ConfiguredApiHandler)


def main() -> None:
    server = create_server()
    print(f"TradeLens backend listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping backend")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
