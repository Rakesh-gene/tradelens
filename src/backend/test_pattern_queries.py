from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import unittest

from pattern_engine.query_service import PatternQueryService, _default_filters, browser_payload
from pattern_engine.enums import SUPPORTED_PATTERN_TYPES
from repositories.pattern_queries import (
    InMemoryPatternQueryRepository,
    PostgresPatternQueryRepository,
)


_DATE = date(2026, 9, 5)


def _pattern(identifier="p1", state="READY", score="88"):
    return {
        "id": identifier, "isin": "INE000000001", "pattern_class": "BASE",
        "pattern_type": "BASE-VCP", "variant": "VCP-3C",
        "start_date": date(2026, 8, 1), "detected_date": date(2026, 8, 20),
        "last_updated_date": _DATE, "terminal_date": None, "state": state,
        "quality_score": Decimal("90"), "maturity_score": Decimal("84"),
        "context_score": Decimal("76"), "setup_score": Decimal(score),
        "pivot_price": Decimal("100"), "support_price": Decimal("90"),
        "invalidation_price": Decimal("88"),
        "measurements": {"depth_pct": Decimal("12"), "scoring": {"context_inputs": {"liquidity": Decimal("100")}, "setup_contributions": {"quality": Decimal("31.5")}, "maturity_band": "READY"}},
        "supporting_patterns": ["TREND-S2"], "engine_version": "v1",
        "configuration_version": "v1", "feature_version": "fv1", "adjustment_version": "av1",
    }


class PatternQueryServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryPatternQueryRepository(
            patterns=[_pattern(), _pattern("p2", "TRIGGERED", "70")],
            events=[{"id": "e1", "pattern_instance_id": "p1", "event_type": "PATTERN_DETECTED", "effective_date": _DATE, "recorded_at": datetime(2026, 9, 5, tzinfo=timezone.utc), "previous_state": None, "new_state": "READY", "previous_values": {}, "new_values": {"state": "READY"}}],
            securities=[{"isin": "INE000000001", "symbol": "EXAMPLE", "company_name": "Example Ltd", "sector_code": "TECH", "sector_name": "Technology"}],
            features=[{"isin": "INE000000001", "trading_date": _DATE, "close_price": Decimal("98"), "relative_strength_6m": Decimal("91"), "relative_strength_percentile": Decimal("94"), "ema_20": Decimal("95"), "sma_50": Decimal("90"), "sma_200": Decimal("80"), "median_volume_20": Decimal("1000"), "median_traded_value_20": Decimal("25000000")}],
            bars=[{"isin": "INE000000001", "adjustment_version": "av1", "trading_date": _DATE - timedelta(days=1), "open_price": Decimal("96"), "high_price": Decimal("100"), "low_price": Decimal("95"), "close_price": Decimal("98"), "volume": Decimal("1000")}],
            actions=[{"source_event_key": "action-1", "isin": "INE000000001", "action_type": "SPLIT", "ex_date": _DATE - timedelta(days=2), "raw_description": "Stock split"}],
            run={"status": "COMPLETED", "finished_at": datetime(2026, 9, 5, tzinfo=timezone.utc), "securities_completed": 1, "securities_failed": 0},
        )
        self.service = PatternQueryService(self.repository)

    def test_overview_returns_ranked_contract_and_numeric_browser_payload(self):
        payload = browser_payload(self.service.overview({"asOf": [_DATE.isoformat()]}))
        self.assertEqual(_DATE.isoformat(), payload["dataAsOf"])
        self.assertEqual(1, len(payload["topSetups"]))
        self.assertEqual(70.0, payload["topSetups"][0]["setupScore"])
        self.assertEqual("EXAMPLE", payload["topSetups"][0]["security"]["symbol"])

    def test_setups_validates_filters_and_uses_repeated_states(self):
        payload = self.service.setups({"asOf": [_DATE.isoformat()], "state": ["READY", "CONFIRMED"], "minSetupScore": ["80"], "pageSize": ["10"]})
        self.assertEqual(["p1"], [item["patternInstanceId"] for item in payload["items"]])
        with self.assertRaisesRegex(ValueError, "Invalid patternClass"):
            self.service.setups({"patternClass": ["UNKNOWN"]})
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self.service.setups({"minSetupScore": ["101"]})

    def test_best_fit_ranks_each_active_lifecycle_state_with_explanations(self):
        payload = browser_payload(self.service.setups({"pageSize": ["10"]}))

        self.assertEqual("best-fit-v1", payload["ranking"]["methodologyVersion"])
        self.assertEqual("lifecycleState", payload["ranking"]["peerGroup"])
        self.assertFalse(payload["ranking"]["historicalOutcomesIncluded"])
        self.assertEqual(1, len(payload["items"]))
        for item in payload["items"]:
            self.assertEqual(1, item["bestFit"]["rankWithinState"])
            self.assertEqual(100.0, item["bestFit"]["percentileWithinState"])
            self.assertEqual("LEADING", item["bestFit"]["tier"])
            self.assertIsNone(item["bestFit"]["historicalProbability"])

    def test_pattern_type_facets_include_the_complete_supported_inventory(self):
        payload = self.service.setups({"pageSize": ["10"]})
        types = payload["facets"]["patternTypes"]

        self.assertEqual(list(SUPPORTED_PATTERN_TYPES), [item["value"] for item in types])
        self.assertEqual(2, next(item["count"] for item in types if item["value"] == "BASE-VCP"))
        self.assertIn("COMP-IB", [item["value"] for item in types])
        self.assertIn("BRK-MULTIY", [item["value"] for item in types])

    def test_global_search_resolves_company_name_to_security_isin(self):
        self.repository.securities["INE000000099"] = {
            "isin": "INE000000099", "symbol": "NOTEXAMPLE",
            "company_name": "The Example Company",
        }
        payload = self.service.search_securities({"q": ["example"], "limit": ["8"]})

        self.assertEqual(1, len(payload["items"]))
        self.assertEqual("INE000000001", payload["items"][0]["isin"])
        self.assertEqual("EXAMPLE", payload["items"][0]["symbol"])
        with self.assertRaisesRegex(ValueError, "at least two"):
            self.service.search_securities({"q": ["E"]})

    def test_detail_events_and_fingerprint_expose_evidence_and_lineage(self):
        detail = self.service.pattern("p1")["pattern"]
        events = self.service.events("p1", {"pageSize": ["10"]})["items"]
        fingerprint = self.service.fingerprint("INE000000001", {"asOf": [_DATE.isoformat()]})
        self.assertEqual(Decimal("12"), detail["measurements"]["depth_pct"])
        self.assertEqual("v1", detail["lineage"]["engineVersion"])
        self.assertEqual("PATTERN_DETECTED", events[0]["eventType"])
        self.assertEqual("BASE-VCP", fingerprint["primarySetup"]["patternType"])
        self.assertEqual("READY", fingerprint["primarySetup"]["maturityBand"])
        self.assertEqual(Decimal("91"), fingerprint["relativeStrength"]["sixMonth"])
        self.assertEqual(2, len(detail["allEvidence"]))

    def test_chart_returns_bounded_candles_and_key_trade_levels(self):
        chart = self.service.chart("p1", {"range": ["3m"]})
        self.assertEqual(1, len(chart["candles"]))
        self.assertEqual(Decimal("100"), chart["levels"]["pivot"])
        self.assertEqual(date(2026, 8, 20), chart["markerDate"])
        self.assertEqual(2, len(chart["evidence"]))
        self.assertEqual("SPLIT", chart["corporateActions"][0]["actionType"])
        self.assertEqual("3m", chart["range"])
        with self.assertRaisesRegex(ValueError, "range must be"):
            self.service.chart("p1", {"range": ["forever"]})

        security_chart = self.service.security_chart("INE000000001", {"asOf": [_DATE.isoformat()], "range": ["6m"]})
        self.assertTrue(security_chart["adjusted"])
        self.assertEqual("av1", security_chart["adjustmentVersion"])
        self.assertEqual(1, len(security_chart["candles"]))
        self.assertEqual(Decimal("100"), security_chart["levels"]["pivot"])

    def test_missing_resources_are_not_found(self):
        with self.assertRaises(LookupError): self.service.pattern("missing")
        with self.assertRaises(LookupError): self.service.fingerprint("missing", {})


class CapturingPatternQueryRepository(PostgresPatternQueryRepository):
    def __init__(self):
        self.statements = []
        self.parameters = []

    def _fetch_all(self, statement, parameters):
        self.statements.append(statement)
        self.parameters.append(parameters)
        if "WITH requested_date" in statement:
            return [{"data_as_of": _DATE}]
        return []


class PatternQueryPerformanceRegressionTestCase(unittest.TestCase):
    def test_security_search_uses_symbol_and_company_name(self):
        repository = CapturingPatternQueryRepository()

        repository.search_securities("reliance", 8)

        statement = repository.statements[-1]
        self.assertIn("symbol ILIKE", statement)
        self.assertIn("company_name ILIKE", statement)
        self.assertNotIn("isin ILIKE", statement)
        self.assertEqual("reliance%", repository.parameters[-1][0])

    def test_chart_query_joins_same_session_indicator_values(self):
        repository = CapturingPatternQueryRepository()
        repository.list_chart_bars("INE000000001", "av1", _DATE, _DATE - timedelta(days=30))
        statement = repository.statements[-1]
        self.assertIn("feature.trading_date = bars.trading_date", statement)
        self.assertIn("features.ema_20", statement)
        self.assertEqual(("INE000000001", "av1", _DATE - timedelta(days=30), _DATE), repository.parameters[-1])

    def test_overview_reads_only_the_selected_feature_session(self):
        repository = CapturingPatternQueryRepository()

        repository.overview_summary(_DATE)

        statement = repository.statements[-1]
        self.assertIn("WHERE trading_date = COALESCE", statement)
        self.assertNotIn("WHERE trading_date <= (SELECT value FROM selected_date)", statement)

    def test_active_setup_ranking_happens_before_feature_lookups(self):
        repository = CapturingPatternQueryRepository()
        filters = _default_filters(_DATE)
        filters["states"] = ("READY", "TRIGGERED", "CONFIRMED")

        repository.list_setups(filters, 6, 0)

        statement = repository.statements[-1]
        self.assertIn("p.terminal_date IS NULL", statement)
        self.assertIn("selected_setups AS", statement)
        self.assertIn("PARTITION BY p.state", statement)
        self.assertIn("best_fit_score", statement)
        self.assertLess(statement.index("selected_setups AS"), statement.index("LEFT JOIN LATERAL"))

    def test_overview_indexes_are_an_append_only_migration(self):
        migration = (
            Path(__file__).resolve().parent
            / "migrations"
            / "020_optimize_overview_queries.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("IF NOT EXISTS", migration)
        self.assertIn("pattern_instances_overview_active_idx", migration)
        self.assertIn("technical_features_latest_version_idx", migration)


if __name__ == "__main__":
    unittest.main()
