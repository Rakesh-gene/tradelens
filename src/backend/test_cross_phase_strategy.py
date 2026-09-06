"""Phase 18 cross-phase acceptance tests over official and synthetic fixtures."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import unittest

from data_pipeline.adjustments import AdjustmentRequest, AdjustmentService
from data_pipeline.normalization import (
    corporate_action_record,
    parse_corporate_actions_response,
    parse_equity_history_response,
    raw_bar_record,
)
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.features import FeatureService, compute_features
from pattern_engine.lifecycle import PatternLifecycleService
from pattern_engine.models import DetectionContext
from pattern_engine.supporting_detectors import detect_supporting_patterns
from pattern_engine.swings import SwingZoneService, build_price_zones, detect_swings
from repositories.patterns import InMemoryPatternRepository


FIXTURES = Path(__file__).resolve().parent / "fixtures"
RELIANCE_ISIN = "INE002A01018"


class PipelineRepository:
    """Small behavioral fake spanning the Phase 5–7 repository contracts."""

    def __init__(self, raw_bars, actions=()):
        self.raw_bars = list(raw_bars)
        self.actions = list(actions)
        self.adjusted_bars = []
        self.features = []
        self.swings = []
        self.zones = []

    @staticmethod
    def _within(rows, from_date, to_date):
        return [row for row in rows if from_date <= row["trading_date"] <= to_date]

    def load_raw_bars(self, isin, from_date, to_date):
        return self._within([row for row in self.raw_bars if row["isin"] == isin], from_date, to_date)

    def load_corporate_actions(self, isin, from_date, to_date, *, as_of=None):
        rows = [row for row in self.actions if row["isin"] == isin and from_date <= row["ex_date"] <= to_date]
        return [row for row in rows if as_of is None or row.get("announcement_date") is None or row["announcement_date"] <= as_of.date()]

    def upsert_adjusted_bars(self, rows):
        for row in rows:
            key = (row["isin"], row["trading_date"], row["adjustment_version"])
            self.adjusted_bars = [existing for existing in self.adjusted_bars if (existing["isin"], existing["trading_date"], existing["adjustment_version"]) != key]
            self.adjusted_bars.append(dict(row))
        return len(rows)

    def load_adjusted_bars(self, isin, from_date, to_date, adjustment_version):
        rows = [row for row in self.adjusted_bars if row["isin"] == isin and row["adjustment_version"] == adjustment_version]
        return sorted(self._within(rows, from_date, to_date), key=lambda row: row["trading_date"])

    def upsert_technical_features(self, rows):
        for row in rows:
            key = (row["isin"], row["trading_date"], row["feature_version"])
            self.features = [existing for existing in self.features if (existing["isin"], existing["trading_date"], existing["feature_version"]) != key]
            self.features.append(dict(row))
        return len(rows)

    def load_technical_features(self, isin, from_date, to_date, feature_version):
        rows = [row for row in self.features if row["isin"] == isin and row["feature_version"] == feature_version]
        return sorted(self._within(rows, from_date, to_date), key=lambda row: row["trading_date"])

    def upsert_swing_points(self, rows):
        self.swings = [dict(row) for row in rows]
        return len(rows)

    def upsert_price_zones(self, rows):
        self.zones = [dict(row) for row in rows]
        return len(rows)


def _load_json(relative_path):
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


class RelianceCrossPhaseTestCase(unittest.TestCase):
    def setUp(self):
        self.snapshot = _load_json("nse/reliance_phase18_snapshot.json")

    def _repository_from_snapshot(self):
        history = parse_equity_history_response(self.snapshot["history"], "RELIANCE")
        actions = parse_corporate_actions_response(
            {"data": self.snapshot["corporateActions"]}, "RELIANCE"
        )
        raw = [raw_bar_record(record, RELIANCE_ISIN, "phase18-source") for record in history]
        action_rows = [
            corporate_action_record(record, RELIANCE_ISIN, "phase18-actions")
            for record in actions
        ]
        return PipelineRepository(raw, action_rows)

    def test_official_nse_response_flows_through_adjustments_and_features(self):
        repository = self._repository_from_snapshot()
        adjustment = AdjustmentService(repository).rebuild(
            AdjustmentRequest(
                RELIANCE_ISIN, date(2024, 1, 1), date(2024, 10, 28),
                adjustment_version="phase18-adjusted-v1",
            )
        )

        self.assertEqual(5, adjustment.rows_written)
        self.assertEqual(Decimal("0.5"), repository.adjusted_bars[0]["price_adjustment_factor"])
        self.assertEqual(4030540, repository.adjusted_bars[0]["volume"])
        written = FeatureService(repository).rebuild(
            RELIANCE_ISIN, date(2024, 1, 1), date(2024, 1, 5),
            adjustment.adjustment_version, "phase18-features-v1",
        )

        self.assertEqual(5, written)
        self.assertIsNotNone(repository.features[-1]["atr_5"])
        self.assertEqual(adjustment.adjustment_version, repository.features[-1]["data_version"])

    def test_source_correction_recomputes_only_the_affected_security_suffix(self):
        repository = self._repository_from_snapshot()
        service = AdjustmentService(repository)
        first = service.rebuild(AdjustmentRequest(
            RELIANCE_ISIN, date(2024, 1, 1), date(2024, 10, 28),
            adjustment_version="phase18-adjusted-v1",
        ))
        features = FeatureService(repository)
        features.rebuild(
            RELIANCE_ISIN, date(2024, 1, 1), date(2024, 1, 5),
            first.adjustment_version, "phase18-features-v1",
        )
        before = {row["trading_date"]: row["input_checksum"] for row in repository.features}
        corrected = next(row for row in repository.raw_bars if row["trading_date"] == date(2024, 1, 5))
        corrected.update(close_price=Decimal("2608.70"), source_checksum="official-correction", raw_revision=2)

        second = service.rebuild(AdjustmentRequest(
            RELIANCE_ISIN, date(2024, 1, 1), date(2024, 10, 28),
            adjustment_version="phase18-adjusted-v1",
        ))
        features.rebuild(
            RELIANCE_ISIN, date(2024, 1, 1), date(2024, 1, 5),
            second.adjustment_version, "phase18-features-v1",
            changed_from_date=date(2024, 1, 5),
        )
        after = {row["trading_date"]: row["input_checksum"] for row in repository.features}

        self.assertEqual(before[date(2024, 1, 4)], after[date(2024, 1, 4)])
        self.assertNotEqual(before[date(2024, 1, 5)], after[date(2024, 1, 5)])
        self.assertTrue(all(row["isin"] == RELIANCE_ISIN for row in repository.features))

    def test_adjusted_series_reaches_swing_detector_candidate_and_immutable_event(self):
        configuration = load_pattern_engine_configuration()
        start = date(2024, 1, 1)
        bars = []
        for index, spread in enumerate((14, 12, 10, 8, 6, 4, 2)):
            center = Decimal("2600") + index
            bars.append({
                "isin": RELIANCE_ISIN, "trading_date": start + timedelta(days=index),
                "open_price": center, "high_price": center + Decimal(spread) / 2,
                "low_price": center - Decimal(spread) / 2, "close_price": center,
                "volume": 4_000_000 - index * 100_000,
            })
        feature_rows = compute_features(bars, "phase18-features-v1", "phase18-adjusted-v1")
        feature_by_date = {row["trading_date"]: row for row in feature_rows}
        swings = detect_swings(bars, feature_by_date)
        zones = build_price_zones(swings)
        context = DetectionContext(bars[-1]["trading_date"], {}, None, (), configuration.version)
        candidates = detect_supporting_patterns(
            {"isin": RELIANCE_ISIN, "symbol": "RELIANCE"},
            bars, feature_rows, swings, zones, context, configuration,
        )
        candidate = next(item for item in candidates if item.pattern_type == "COMP-NR7")
        patterns = InMemoryPatternRepository()
        result = PatternLifecycleService(patterns, configuration).apply_candidate(
            candidate, engine_version="phase18-engine-v1",
            feature_version="phase18-features-v1",
            adjustment_version="phase18-adjusted-v1",
        )

        self.assertEqual("created", result.action)
        self.assertEqual("COMP-NR7", result.instance["pattern_type"])
        self.assertEqual(1, len(patterns.events))
        self.assertEqual("PATTERN_DETECTED", patterns.events[0]["event_type"])


class GoldenScenarioCatalogTestCase(unittest.TestCase):
    def test_catalog_is_named_explainable_and_covers_the_v1_inventory(self):
        catalog = _load_json("golden/pattern_scenarios.json")
        scenarios = catalog["scenarios"]
        covered = {
            identifier
            for scenario in scenarios
            for identifier in (
                [scenario["patternType"]]
                + ([scenario["variant"]] if scenario.get("variant") else [])
                + scenario.get("coveredPatternTypes", [])
            )
        }
        required = {
            "VCP-2C", "VCP-3C", "VCP-4C", "VCP-5C", "BASE-FLAT", "BASE-52WH",
            "BRK-RANGE", "BRK-52WH", "BRK-ATH", "BRK-2Y", "BRK-3Y", "BRK-5Y",
            "PB-BRKRET", "PB-EMA20", "PB-SMA50-T1", "PB-SMA50-T2", "PB-SMA50-T3+",
            "TREND-HHHL", "TREND-S2", "TREND-MA", "BASE-TIGHT", "COMP-NR7",
            "COMP-IB1", "COMP-IB2", "COMP-IB3", "COMP-ATR", "COMP-RANGE",
            "MOM-ACC", "MOM-RSL", "MOM-RSB", "VOL-DRY", "VOL-EXP",
            "FAIL-BRK", "FAIL-BASE", "FAIL-EMA20", "FAIL-SMA50", "FAIL-STRUCT",
        }

        self.assertEqual(len(scenarios), len({scenario["name"] for scenario in scenarios}))
        self.assertTrue(required <= covered, sorted(required - covered))
        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                self.assertIsInstance(scenario["shouldDetect"], bool)
                self.assertTrue(scenario["reason"].strip())
                self.assertIn("pivot", scenario["expected"])
                self.assertIn("state", scenario["expected"])
                self.assertIn("measurements", scenario["expected"])
                self.assertIn("scores", scenario["expected"])


if __name__ == "__main__":
    unittest.main()
