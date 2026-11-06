"""Atomic persistence of allowlisted local chat settings, preserving other config."""
import os
from pathlib import Path
import tempfile

CHAT_KEYS = {"CHAT_ENABLED", "CHAT_PROVIDER", "ONTOP_URL", "OLLAMA_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS"}


class EnvChatConfigurationRepository:
    def __init__(self, path):
        self.path = Path(path)

    def save(self, values):
        if set(values) - CHAT_KEYS:
            raise ValueError("Unsupported configuration setting")
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        seen = set()
        result = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
            if key in values:
                result.append(f"{key}={values[key]}")
                seen.add(key)
            else:
                result.append(line)
        result.extend(f"{key}={value}" for key, value in values.items() if key not in seen)
        descriptor, temporary = tempfile.mkstemp(prefix=".chat-config-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write("\n".join(result) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
