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
            "is_admin": False,
            "theme_preference": "ember",
        }
        self._users[user["email"]] = user
        return user

    def update_theme_preference(self, user_id: str, theme: str) -> dict[str, object] | None:
        user = next((item for item in self._users.values() if str(item["id"]) == str(user_id)), None)
        if user is not None:
            user["theme_preference"] = theme
        return user
