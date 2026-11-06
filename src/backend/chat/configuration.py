"""Construct optional chat dependencies and report configuration without secrets."""
from chat.gemini_client import GeminiClient
from chat.ollama_client import OllamaClient
from chat.service import ChatService
from repositories.knowledge_graph import OntopKnowledgeGraphRepository
from threading import Lock
from typing import Protocol
from chat.errors import ChatError


def _provider(environment):
    return environment.get("CHAT_PROVIDER", "ollama").strip().lower()


def _timeout_seconds(environment):
    key = "OLLAMA_TIMEOUT_SECONDS" if _provider(environment) == "ollama" else "GEMINI_TIMEOUT_SECONDS"
    value = int(environment.get(key, "45"))
    if not 5 <= value <= 120:
        raise ValueError("Model timeout must be between 5 and 120 seconds.")
    return value


def build_chat_service(environment, security_search=None):
    enabled = environment.get("CHAT_ENABLED", "false").strip().lower() == "true"
    endpoint = environment.get("ONTOP_URL", "http://127.0.0.1:8088/sparql").strip()
    key = environment.get("GEMINI_API_KEY", "").strip()
    provider = _provider(environment)
    model_id = environment.get("OLLAMA_MODEL", "gemma4:31b-cloud").strip() if provider == "ollama" else environment.get("GEMINI_MODEL", "").strip()
    ollama_url = environment.get("OLLAMA_URL", "http://127.0.0.1:11434").strip()
    graph = model = None
    checks = [
        {"setting": "CHAT_ENABLED", "label": "Chat feature", "status": "configured" if enabled else "disabled"},
        {"setting": "ONTOP_URL", "label": "Ontology endpoint", "status": "configured"},
        {"setting": "CHAT_PROVIDER", "label": "Model provider", "status": "configured" if provider in {"ollama", "gemini"} else "invalid"},
        {"setting": "OLLAMA_MODEL" if provider == "ollama" else "GEMINI_MODEL", "label": "Chat model", "status": "configured" if model_id else "missing"},
    ]
    try:
        timeout = _timeout_seconds(environment)
        timeout_status = "configured"
    except (TypeError, ValueError):
        timeout, timeout_status = 45, "invalid"
    checks.append({"setting": "OLLAMA_TIMEOUT_SECONDS" if provider == "ollama" else "GEMINI_TIMEOUT_SECONDS", "label": "Model timeout", "status": timeout_status})
    if provider == "gemini":
        checks.append({"setting": "GEMINI_API_KEY", "label": "Gemini API key", "status": "configured" if key else "missing"})
    try:
        graph = OntopKnowledgeGraphRepository(endpoint)
    except ValueError:
        checks[1]["status"] = "invalid"
    if model_id:
        try:
            model = OllamaClient(ollama_url, model_id, timeout=timeout) if provider == "ollama" else GeminiClient(key, model_id, timeout=timeout)
        except ValueError:
            checks[3]["status"] = "invalid"
    ready = enabled and all(check["status"] == "configured" for check in checks)
    configuration = {
        "checks": checks,
        "requiresRestart": False,
        "help": "An administrator can update chat settings in this widget. Configured does not mean connectivity has been verified.",
    }
    return ChatService(graph if ready else None, model if ready else None, configuration=configuration, security_search=security_search)


class ConfigurationRepository(Protocol):
    def save(self, values: dict[str, str]) -> None: ...


class ChatConfigurationService:
    def __init__(self, repository: ConfigurationRepository, environment, security_search=None):
        self.repository, self.environment, self.security_search = repository, environment, security_search
        self.lock = Lock()
        self.chat_service = build_chat_service(environment, security_search)

    def get(self):
        with self.lock:
            return self._public()

    def _public(self):
        try:
            timeout = _timeout_seconds(self.environment)
        except (TypeError, ValueError):
            timeout = 45
        return {"enabled": self.environment.get("CHAT_ENABLED", "false").lower() == "true",
                "ontologyUrl": self.environment.get("ONTOP_URL", "http://127.0.0.1:8088/sparql"),
                "provider": _provider(self.environment),
                "ollamaUrl": self.environment.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                "model": self.environment.get("OLLAMA_MODEL", "gemma4:31b-cloud") if _provider(self.environment) == "ollama" else self.environment.get("GEMINI_MODEL", ""),
                "apiKeyConfigured": bool(self.environment.get("GEMINI_API_KEY", "").strip()),
                "timeoutSeconds": timeout}

    def save(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"enabled", "ontologyUrl", "model", "apiKey", "timeoutSeconds", "provider", "ollamaUrl"} or not {"enabled", "ontologyUrl", "model"} <= set(payload):
            raise ValueError("Provide enabled, ontologyUrl, model, and an optional API key.")
        if not isinstance(payload["enabled"], bool):
            raise ValueError("Enabled must be true or false.")
        if "timeoutSeconds" in payload and (type(payload["timeoutSeconds"]) is not int or not 5 <= payload["timeoutSeconds"] <= 120):
            raise ValueError("Model timeout must be an integer between 5 and 120 seconds.")
        for key in ("ontologyUrl", "model", "apiKey", "provider", "ollamaUrl"):
            value = payload.get(key, "")
            if not isinstance(value, str) or len(value) > 4096 or any(char in value for char in "\r\n\x00"):
                raise ValueError("Configuration values must be single-line text.")
        with self.lock:
            provider = payload.get("provider", _provider(self.environment)).strip().lower()
            if provider not in {"ollama", "gemini"}:
                raise ValueError("Choose Ollama or Gemini as the model provider.")
            model_key = "OLLAMA_MODEL" if provider == "ollama" else "GEMINI_MODEL"
            values = {"CHAT_ENABLED": str(payload["enabled"]).lower(), "ONTOP_URL": payload["ontologyUrl"].strip(), "CHAT_PROVIDER": provider, model_key: payload["model"].strip()}
            values["OLLAMA_URL"] = payload.get("ollamaUrl", self.environment.get("OLLAMA_URL", "http://127.0.0.1:11434")).strip()
            if "timeoutSeconds" in payload:
                values["OLLAMA_TIMEOUT_SECONDS" if provider == "ollama" else "GEMINI_TIMEOUT_SECONDS"] = str(payload["timeoutSeconds"])
            values["GEMINI_API_KEY"] = payload.get("apiKey", "").strip() or self.environment.get("GEMINI_API_KEY", "").strip()
            candidate = {**self.environment, **values}
            OntopKnowledgeGraphRepository(values["ONTOP_URL"])
            if values[model_key]:
                if provider == "ollama":
                    OllamaClient(values["OLLAMA_URL"], values[model_key])
                else:
                    GeminiClient("", values[model_key])
            service = build_chat_service(candidate, self.security_search)
            if payload["enabled"] and not service.capabilities()["enabled"]:
                raise ValueError("Set a valid provider, endpoint and model before enabling chat. Gemini also requires an API key.")
            try:
                self.repository.save(values)
            except OSError:
                raise ChatError("CONFIGURATION_SAVE_FAILED", "The server could not save chat settings. Check its configuration-file permissions.") from None
            self.environment.update(values)
            self.chat_service = service
            return service, self._public()
