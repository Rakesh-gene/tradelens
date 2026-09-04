from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RegistrationResult:
    user_id: str
    email: str


@dataclass(slots=True)
class AuthenticationResult:
    access_token: str
    user_id: str
    email: str
    is_admin: bool
