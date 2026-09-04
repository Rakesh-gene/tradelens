from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from auth.service import AuthService, UserRepository
from repositories.memory import InMemoryUserRepository
from repositories.postgres import PostgresUserRepository
from server_http.api import ApiHandler

HOST = "127.0.0.1"
PORT = 9004
DEVELOPMENT_JWT_SECRET = "change-this-tradelens-development-jwt-secret"


def load_local_environment() -> None:
    """Load backend/.env for local development.

    The checked-out local configuration is deliberately authoritative so another
    project-level DATABASE_URL in a developer shell cannot point TradeLens at a
    different database.
    """
    environment_file = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(environment_file):
        return
    with open(environment_file, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            os.environ[key.strip()] = value.strip()


load_local_environment()


def build_repository() -> UserRepository:
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return PostgresUserRepository(dsn)
    return InMemoryUserRepository()


def create_server(host: str = HOST, port: int = PORT, repository: UserRepository | None = None) -> ThreadingHTTPServer:
    repository = repository or build_repository()
    service = AuthService(repository, os.getenv("JWT_SECRET", DEVELOPMENT_JWT_SECRET))

    class ConfiguredApiHandler(ApiHandler):
        pass

    ConfiguredApiHandler.service = service
    return ThreadingHTTPServer((host, port), ConfiguredApiHandler)
