from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from auth.service import AuthService, UserRepository
from repositories.memory import InMemoryUserRepository
from repositories.postgres import PostgresUserRepository
from server_http.api import ApiHandler

HOST = "127.0.0.1"
PORT = 9004


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
