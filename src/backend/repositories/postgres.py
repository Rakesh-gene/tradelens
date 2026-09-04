from __future__ import annotations

from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional at test time
    psycopg = None


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

    def get_by_email(self, email: str) -> dict[str, object] | None:
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

    def create_user(self, email: str, password_hash: str) -> dict[str, object]:
        user_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (id, email, password_hash) VALUES (%s, %s, %s)",
                    (user_id, email.lower(), password_hash),
                )
            connection.commit()
        return {"id": user_id, "email": email.lower(), "password_hash": password_hash}
