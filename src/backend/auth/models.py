from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RegistrationResult:
    user_id: str
    email: str
