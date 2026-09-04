from __future__ import annotations

from uuid import uuid4


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, object]] = {}

    def get_by_email(self, email: str) -> dict[str, object] | None:
        return self._users.get(email.lower())

    def create_user(self, email: str, password_hash: str) -> dict[str, object]:
        user = {
            "id": str(uuid4()),
            "email": email.lower(),
            "password_hash": password_hash,
        }
        self._users[user["email"]] = user
        return user
