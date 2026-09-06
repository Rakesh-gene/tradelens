"""Structured, secret-safe operational events and health diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Callable, Protocol

from pattern_engine.models import serialize_value


_SENSITIVE_FRAGMENTS = ("authorization", "cookie", "password", "secret", "token", "jwt")


class OperationsRepository(Protocol):
    def record_operational_event(self, event: Mapping[str, object]) -> str: ...
    def operational_health(self) -> Mapping[str, object]: ...
    def validate_coverage(self, from_date: date | None, to_date: date | None, limit: int) -> list[dict[str, object]]: ...
    def upsert_anomalies(self, anomalies: list[Mapping[str, object]]) -> int: ...
    def pattern_lineage(self, pattern_id: str) -> Mapping[str, object] | None: ...


class StructuredEventLogger:
    def __init__(self, repository: OperationsRepository | None = None, *, sink: Callable[[str], None] = print) -> None:
        self._repository = repository
        self._sink = sink

    def emit(self, event_type: str, *, level: str = "INFO", **fields):
        event = {
            "occurred_at": datetime.now(timezone.utc), "level": level,
            "event_type": event_type, **_sanitize(fields),
        }
        self._sink(json.dumps(serialize_value(event), sort_keys=True, separators=(",", ":")))
        if self._repository is not None:
            self._repository.record_operational_event(event)
        return event


class OperationalMonitor:
    def __init__(self, repository: OperationsRepository, *, daily_processing_window_minutes=120) -> None:
        self._repository = repository
        self._daily_window_minutes = int(daily_processing_window_minutes)

    def status(self):
        snapshot = dict(self._repository.operational_health())
        snapshot["generatedAt"] = datetime.now(timezone.utc)
        daily = next((row for row in snapshot.get("lastSuccessfulRuns", ()) if row.get("job_type") == "DAILY_DELTA"), None)
        duration = daily.get("duration_ms") if daily else None
        snapshot["dailyProcessingWindow"] = {
            "minutes": self._daily_window_minutes,
            "latestDurationMs": duration,
            "withinWindow": None if duration is None else int(duration) <= self._daily_window_minutes * 60_000,
        }
        return snapshot

    def validate_coverage(self, from_date=None, to_date=None, *, limit=5000, persist=True):
        if from_date and to_date and from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        if not 1 <= limit <= 100_000:
            raise ValueError("limit must be between 1 and 100000")
        rows = self._repository.validate_coverage(from_date, to_date, limit)
        anomalies = [
            {
                "anomaly_type": "MISSING_TRADING_SESSIONS", "severity": "WARNING",
                "isin": row["isin"], "trading_date": None,
                "details": {"missingSessions": row["missing_sessions"], "fromDate": row.get("from_date"), "toDate": row.get("to_date")},
            }
            for row in rows if int(row.get("missing_sessions") or 0) > 0
        ]
        if persist and anomalies:
            self._repository.upsert_anomalies(anomalies)
        return {"checked": len(rows), "anomalyCount": len(anomalies), "items": rows}

    def lineage(self, pattern_id):
        if not str(pattern_id).strip(): raise ValueError("pattern_id is required")
        result = self._repository.pattern_lineage(pattern_id)
        if result is None: raise LookupError("Pattern not found")
        return result


def _sanitize(value):
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if any(fragment in str(key).lower() for fragment in _SENSITIVE_FRAGMENTS) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)): return [_sanitize(item) for item in value]
    return value
