from datetime import date
import json
import unittest

from operations.monitoring import OperationalMonitor, StructuredEventLogger


class FakeOperationsRepository:
    def __init__(self): self.events = []; self.anomalies = []
    def record_operational_event(self, event): self.events.append(dict(event)); return "event-1"
    def operational_health(self): return {"latestRuns": [], "lastSuccessfulRuns": [], "pipeline": {"feature_lag_days": 1}}
    def validate_coverage(self, from_date, to_date, limit):
        return [{"isin": "A", "from_date": from_date, "to_date": to_date, "missing_sessions": 2}, {"isin": "B", "missing_sessions": 0}]
    def upsert_anomalies(self, anomalies): self.anomalies.extend(anomalies); return len(anomalies)
    def pattern_lineage(self, pattern_id): return {"pattern": {"id": pattern_id}, "adjustedBars": [], "corporateActions": [], "features": []}


class OperationsTestCase(unittest.TestCase):
    def test_structured_logger_redacts_sensitive_fields_from_sink_and_storage(self):
        repository = FakeOperationsRepository(); lines = []
        logger = StructuredEventLogger(repository, sink=lines.append)
        logger.emit("request_failed", level="ERROR", run_id="run-1", details={"authorization": "Bearer secret", "nested": {"cookie": "private"}, "status": 403})
        payload = json.loads(lines[0])
        self.assertEqual("[REDACTED]", payload["details"]["authorization"])
        self.assertEqual("[REDACTED]", payload["details"]["nested"]["cookie"])
        self.assertEqual("[REDACTED]", repository.events[0]["details"]["authorization"])

    def test_coverage_validation_persists_only_missing_session_anomalies(self):
        repository = FakeOperationsRepository(); monitor = OperationalMonitor(repository)
        result = monitor.validate_coverage(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(2, result["checked"]); self.assertEqual(1, result["anomalyCount"])
        self.assertEqual("A", repository.anomalies[0]["isin"])

    def test_status_includes_generation_time(self):
        payload = OperationalMonitor(FakeOperationsRepository()).status()
        self.assertIn("generatedAt", payload)
        self.assertEqual(1, payload["pipeline"]["feature_lag_days"])
        self.assertIsNone(payload["dailyProcessingWindow"]["withinWindow"])

    def test_lineage_exposes_source_chain(self):
        payload = OperationalMonitor(FakeOperationsRepository()).lineage("pattern-1")
        self.assertEqual("pattern-1", payload["pattern"]["id"])


if __name__ == "__main__": unittest.main()
