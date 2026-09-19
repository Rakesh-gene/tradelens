from __future__ import annotations

import hashlib
import hmac
import re
from typing import Protocol

from auth.jwt import decode_access_token, issue_access_token
from auth.models import AuthenticationResult, RegistrationResult

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEFAULT_THEME = "ember"
SUPPORTED_THEMES = ("light", "ember", "forest", "ocean", "plum", "slate")


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> dict[str, object] | None:
        ...

    def create_user(self, email: str, password_hash: str) -> dict[str, object]:
        ...

    def update_theme_preference(self, user_id: str, theme: str) -> dict[str, object] | None:
        ...


class AuthService:
    def __init__(self, user_repository: UserRepository, jwt_secret: str) -> None:
        self._user_repository = user_repository
        self._jwt_secret = jwt_secret

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

    def login(self, email: str, password: str) -> AuthenticationResult:
        user = self._user_repository.get_by_email(email.strip().lower())
        if user is None or not hmac.compare_digest(user["password_hash"], self._hash_password(password)):
            raise ValueError("Invalid email or password")
        return AuthenticationResult(
            access_token=issue_access_token(user, self._jwt_secret),
            user_id=user["id"],
            email=user["email"],
            is_admin=bool(user.get("is_admin", False)),
            theme=str(user.get("theme_preference") or DEFAULT_THEME),
        )

    def current_user(self, access_token: str) -> dict[str, object]:
        claims = decode_access_token(access_token, self._jwt_secret)
        user = self._user_repository.get_by_email(str(claims["email"]))
        if user is None or str(user["id"]) != str(claims["sub"]):
            raise ValueError("Invalid or expired access token")
        return {
            "id": user["id"], "email": user["email"],
            "is_admin": bool(user.get("is_admin", False)),
            "theme": str(user.get("theme_preference") or DEFAULT_THEME),
        }

    def update_theme(self, access_token: str, theme: object) -> dict[str, object]:
        user = self.current_user(access_token)
        normalized_theme = str(theme or "").strip().lower()
        if normalized_theme not in SUPPORTED_THEMES:
            raise ValueError("Theme must be one of: " + ", ".join(SUPPORTED_THEMES))
        updated = self._user_repository.update_theme_preference(str(user["id"]), normalized_theme)
        if updated is None:
            raise ValueError("User profile was not found")
        return {
            "id": updated["id"], "email": updated["email"],
            "is_admin": bool(updated.get("is_admin", False)),
            "theme": str(updated.get("theme_preference") or DEFAULT_THEME),
        }

    def renew_access_token(self, access_token: str) -> tuple[dict[str, object], str]:
        """Validate the current session and issue a fresh sliding access token."""
        user = self.current_user(access_token)
        return user, issue_access_token(user, self._jwt_secret)

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
