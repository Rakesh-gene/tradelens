"""Single-capability ontology-grounded assistant, extensible through its catalog."""
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from math import isfinite
import json
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Protocol
from uuid import UUID
from urllib.parse import quote

from chat.errors import ChatError
from chat.questions import setup_question_target
from repositories.knowledge_graph import validated_symbol

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "ontology/catalog.json").read_text(encoding="utf-8"))
CAPABILITY = CATALOG["intents"]["equity_setup_today"]
ACTIVE_STATES = {"DETECTED", "FORMING", "MATURE", "READY", "TRIGGERED", "CONFIRMED"}
INDIA = timezone(timedelta(hours=5, minutes=30))


class KnowledgeGraphRepository(Protocol):
    def current_setups(self, symbol: str) -> list[dict[str, str]]: ...


class AnswerModel(Protocol):
    def summarize(self, evidence: dict, definition: dict) -> dict: ...


def release_manifest():
    files = ["ontology/tradelens.ttl", "ontology/facts.ttl", "ontology/shapes.ttl", "ontology/catalog.json",
             "repositories/semantic/tradelens.r2rml.ttl", "repositories/semantic/lenses.json", "repositories/semantic/queries/equity_setup_today.rq"]
    return {"version": CATALOG["version"], "hashes": {
        name: sha256((ROOT / name).read_bytes()).hexdigest() for name in files
    }}


def _date(value):
    return date.fromisoformat(value) if value else None


def _numeric(row, field, score=False):
    if row.get(field) is None:
        return None
    value = Decimal(row[field])
    if not value.is_finite() or (score and not 0 <= value <= 100) or (not score and value <= 0):
        raise ValueError("Invalid observation")
    number = float(value)
    if not isfinite(number):
        raise ValueError("Observation exceeds supported numeric range")
    return number


class ChatService:
    def __init__(self, graph: KnowledgeGraphRepository | None = None, model: AnswerModel | None = None, *, clock=None, configuration=None, security_search=None):
        self.graph, self.model = graph, model
        self.configuration = configuration
        self.security_search = security_search
        self.clock = clock or (lambda: datetime.now(INDIA).date())
        self._slots = BoundedSemaphore(4)
        self._lock = Lock()
        self._active_users = set()
        self._requests = {}

    def capabilities(self):
        return {"enabled": self.graph is not None and self.model is not None,
                "question": CAPABILITY["question"], "intent": "equity_setup_today",
                "scope": CAPABILITY["scope"], "ontologyVersion": CATALOG["version"],
                "maxMessageLength": 4000, "configuration": self.configuration}

    def answer(self, payload, user_id):
        if not isinstance(payload, dict) or "message" not in payload or set(payload) - {"message", "symbol", "contextSymbol"}:
            raise ValueError("Send a question and optional page context only.")
        message = payload["message"]
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            raise ValueError("The question must contain between 1 and 4000 characters.")
        context_symbol = payload.get("contextSymbol") or payload.get("symbol")
        if context_symbol is not None:
            context_symbol = validated_symbol(context_symbol)
        if not self.capabilities()["enabled"]:
            raise ChatError("CHAT_NOT_CONFIGURED", "Chat requires the Ontop service and a configured chat model. Contact your administrator.")
        with self._lock:
            now = monotonic()
            # Bounded process-local limit for this nonpersistent first slice.
            self._requests = {key: times for key, times in self._requests.items() if times and now - times[-1] < 60}
            times = [t for t in self._requests.get(user_id, []) if now - t < 60]
            if user_id in self._active_users or len(times) >= 6 or len(self._requests) >= 1000:
                raise ChatError("CHAT_RATE_LIMITED", "Please wait before asking again.", 429)
            if not self._slots.acquire(blocking=False):
                raise ChatError("CHAT_BUSY", "The assistant is busy. Please retry shortly.", 429)
            self._active_users.add(user_id)
            self._requests[user_id] = [*times, now]
        try:
            target = self.model.resolve_target(message) if hasattr(self.model, "resolve_target") else setup_question_target(message)
            if target is None and not context_symbol:
                raise ChatError("EQUITY_REQUIRED", "Which equity do you mean? Include its company name or NSE symbol, or open its page.", 400)
            symbol = self._resolve_target(target) if target else context_symbol
            return self._answer(symbol)
        finally:
            with self._lock:
                self._active_users.remove(user_id)
            self._slots.release()

    def _resolve_target(self, target):
        if self.security_search is None:
            return validated_symbol(target)
        matches = self.security_search({"q": [target], "limit": [8]}).get("items", [])
        exact = [item for item in matches if target.casefold() in {str(item.get("symbol", "")).casefold(), str(item.get("name", "")).casefold()}]
        choices = exact or matches
        if len(choices) == 1:
            return validated_symbol(choices[0]["symbol"])
        if not choices:
            raise ChatError("EQUITY_NOT_FOUND", "No equity matched that name. Include its full company name or NSE symbol in your question.", 404)
        labels = ", ".join(str(item["symbol"]) for item in choices)
        raise ChatError("EQUITY_AMBIGUOUS", f"That name matches several equities: {labels}. Please specify one in your question.", 400)

    def _answer(self, symbol):
        rows = self.graph.current_setups(symbol)
        if not rows:
            raise ChatError("EQUITY_NOT_FOUND", "No eligible equity was found for that NSE symbol.", 404)
        try:
            head, today = rows[0], self.clock()
            if any(row.get("symbol") != symbol or row.get("security") != head.get("security") for row in rows):
                raise ValueError("Ambiguous security")
            data_date, feature_date, pattern_date = (_date(head.get(key)) for key in ("dataAsOf", "featureDate", "patternDate"))
            if any(value and value > today for value in (data_date, feature_date, pattern_date)):
                raise ValueError("Future evidence")
            if data_date != max((value for value in (feature_date, pattern_date) if value), default=None):
                raise ValueError("Inconsistent evaluation date")
            if any(row.get(key) != head.get(key) for row in rows for key in ("dataAsOf", "featureDate", "patternDate")):
                raise ValueError("Mixed context dates")
            partial = pattern_date is None or (feature_date is not None and (pattern_date is None or feature_date > pattern_date))
            setups, seen = [], set()
            for row in rows[:25]:
                if not row.get("patternId"):
                    continue
                identifier = str(UUID(row["patternId"]))
                if identifier in seen or partial or _date(row.get("evidenceDate")) != data_date:
                    raise ValueError("Conflicting evidence")
                seen.add(identifier)
                state = row["state"].removeprefix("urn:tradelens:ontology:")
                if state not in ACTIVE_STATES or not row.get("snapshot", "").startswith("urn:tradelens:snapshot:"):
                    raise ValueError("Invalid snapshot")
                if not _date(row.get("detectedDate")) or _date(row["detectedDate"]) > data_date:
                    raise ValueError("Invalid detection date")
                setups.append({
                    "sourceId": identifier, "patternInstanceId": identifier,
                    "patternType": row["patternType"], "variant": row.get("variant"), "state": state,
                    "dataAsOf": row["evidenceDate"], "detectedDate": row["detectedDate"], "timeframe": "1D",
                    "scores": {key: _numeric(row, key, True) for key in ("quality", "maturity", "context", "setup")},
                    "levels": {key: _numeric(row, key) for key in ("pivot", "support", "invalidation")},
                    "lineage": {key: row[key] for key in ("engineVersion", "configurationVersion", "featureVersion", "adjustmentVersion")},
                    "href": f"/patterns/{identifier}",
                    # Internal evidence retained for provider grounding, not public navigation.
                    "snapshot": row["snapshot"],
                })
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ChatError("ONTOLOGY_INVALID_EVIDENCE", "The ontology returned inconsistent evidence. Please retry after processing completes.") from None
        warnings = []
        if data_date != today:
            warnings.append("Today's evaluation is unavailable. The date shown is the latest recorded EOD evidence; this may be the previous trading session.")
        if partial:
            warnings.append("Pattern evaluation is missing or behind available features. An absence of returned setups is not a verified zero.")
        if len(rows) > 25:
            warnings.append("Only the first 25 primary setups are shown. This is not a complete setup count.")
        missing = sorted({key for item in setups for key, value in {**item["scores"], **item["levels"]}.items() if value is None})
        if missing:
            warnings.append("Some setups have missing evidence: " + ", ".join(missing) + ".")
        code = "EVIDENCE_UNAVAILABLE" if partial else "SETUPS_PRESENT" if setups else "NO_CURRENT_SETUP"
        evidence = {"summaryCode": code, "symbol": symbol, "dataAsOf": data_date.isoformat() if data_date else None,
                    "setups": setups, "warnings": warnings}
        gemini_error = None
        try:
            model = self.model.summarize(evidence, CAPABILITY)
        except ChatError as error:
            if error.code not in {"UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE", "UPSTREAM_RATE_LIMITED",
                                  "UPSTREAM_NETWORK_BLOCKED", "UPSTREAM_CONNECTION_FAILED",
                                  "UPSTREAM_DNS_FAILED", "UPSTREAM_TLS_FAILED"}:
                raise
            # The ontology query already succeeded and all returned facts passed
            # validation. Preserve them, with an explicit provider-failure label.
            # Never substitute service/API data or pretend the model succeeded.
            gemini_error = error.code
            model = {"model": None}
            warnings.append(f"Model explanation unavailable ({error.code}). Showing validated Ontop evidence only; no LLM explanation was generated.")
        answer = {
            "SETUPS_PRESENT": f"{symbol} has the following recorded active daily primary setups. Review each setup's state and evidence below.",
            "NO_CURRENT_SETUP": f"No active daily primary setup was returned for {symbol} at the latest recorded evaluation.",
            "EVIDENCE_UNAVAILABLE": f"There is not enough current pattern evidence to establish {symbol}'s setup.",
        }[code]
        versions = lambda key: sorted({item["lineage"][key] for item in setups})
        single = lambda key: versions(key)[0] if len(versions(key)) == 1 else None
        return {
            "intent": "equity_setup_today", "question": CAPABILITY["question"], "answer": answer,
            "security": {"symbol": symbol, "name": head.get("name"), "href": f"/securities/{quote(symbol, safe='')}"},
            "dataAsOf": evidence["dataAsOf"], "requestedAsOf": today.isoformat(),
            "generatedAt": datetime.now(timezone.utc).isoformat(), "isStale": data_date != today,
            "isPartial": partial or bool(missing) or len(rows) > 25 or gemini_error is not None, "warnings": warnings,
            "status": "insufficientEvidence" if partial else "answered",
            "engineVersion": single("engineVersion"), "configurationVersion": single("configurationVersion"),
            "setups": [{key: value for key, value in item.items() if key != "snapshot"} for item in setups],
            "provenance": {"queryId": "equity_setup_today", "mappingIds": ["Equity", "Snapshot", "ScoreLink", "Score"],
                           "release": release_manifest(), "model": model["model"],
                           "provider": getattr(self.model, "provider", "gemini"),
                           "answerMode": "ontologyEvidenceOnly" if gemini_error else "ontologyGrounded",
                           "modelErrorCode": gemini_error,
                           "geminiErrorCode": gemini_error},
            "disclaimer": "Setup scores rank evidence. They are not win probabilities or investment recommendations.",
        }
