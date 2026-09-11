from __future__ import annotations

from datetime import date
import unittest

from data_pipeline.models import NseEquityClassification, freeze_json_value
from data_pipeline.nse_classification_collector import NseClassificationCollector
from data_pipeline.nse_api import NseRequestError
from data_pipeline.normalization import NseDataValidationError


class FakeClient:
    metrics = {"requestAttempts": 2}

    def fetch_equity_classification(self, symbol, expected_isin):
        if symbol == "BROKEN":
            raise RuntimeError("NSE unavailable")
        if symbol == "UNCLASSIFIED":
            raise NseDataValidationError(symbol, "industryInfo", "is missing")
        if symbol == "NOTFOUND":
            raise NseRequestError("HTTP_ERROR", "NSE returned HTTP 404", status_code=404)
        return NseEquityClassification(
            symbol, expected_isin, "Commodities", "Energy", "Petroleum Products",
            "Refineries & Marketing", "checksum", freeze_json_value({"info": {"symbol": symbol}}),
        )


class FakeRepository:
    def __init__(self):
        self.rows = [
            {"symbol": "RELIANCE", "isin": "INE002A01018"},
            {"symbol": "BROKEN", "isin": "INE000000002"},
        ]
        self.saved = []
        self.failures = []
        self.missing = []

    def list_classifications_due(self, limit, stale_days):
        return self.rows[:limit] if limit is not None else self.rows

    def upsert_classification(self, value, effective_from):
        self.saved.append((value, effective_from))
        return True

    def mark_classification_failed(self, isin, error):
        self.failures.append((isin, error))

    def mark_classification_missing(self, isin, reason):
        self.missing.append((isin, reason))


class NseClassificationCollectorTestCase(unittest.TestCase):
    def test_refresh_is_resumable_and_isolates_one_equity_failure(self):
        repository = FakeRepository()
        report = NseClassificationCollector(repository, FakeClient()).refresh_new_and_stale(
            limit=2, effective_from=date(2026, 9, 10)
        )

        self.assertEqual(1, report["completed"])
        self.assertEqual(1, report["failed"])
        self.assertEqual("Energy", repository.saved[0][0]["sector"])
        self.assertEqual("INE000000002", repository.failures[0][0])

    def test_absent_nse_taxonomy_is_recorded_as_missing_not_as_a_run_failure(self):
        repository = FakeRepository()
        repository.rows = [{"symbol": "UNCLASSIFIED", "isin": "INE000000003"}]

        report = NseClassificationCollector(repository, FakeClient()).refresh_new_and_stale(
            limit=1, effective_from=date(2026, 9, 10)
        )

        self.assertEqual(0, report["failed"])
        self.assertEqual(1, report["missing"])
        self.assertEqual("INE000000003", repository.missing[0][0])

    def test_exhausted_nse_404_is_recorded_as_missing(self):
        repository = FakeRepository()
        repository.rows = [{"symbol": "NOTFOUND", "isin": "INE000000004"}]

        report = NseClassificationCollector(repository, FakeClient()).refresh_new_and_stale(
            limit=1, effective_from=date(2026, 9, 10)
        )

        self.assertEqual(0, report["failed"])
        self.assertEqual(1, report["missing"])


if __name__ == "__main__":
    unittest.main()
