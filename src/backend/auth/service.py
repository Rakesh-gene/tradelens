from __future__ import annotations

import hashlib
import re
from typing import Protocol

from auth.models import RegistrationResult

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> dict[str, object] | None:
        ...

    def create_user(self, email: str, password_hash: str) -> dict[str, object]:
        ...


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
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
